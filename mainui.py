from google.appengine.ext.webapp import template
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.datastore import entity_pb
import webapp2
import os
import datetime
import logging
import json as simplejson
import urllib2

class displayPosts(webapp2.RequestHandler):
	def get(self, start_idx, offset_hrs):
		logging.getLogger().setLevel(logging.DEBUG)
		logging.debug('start_idx:' + str(start_idx) + ' offset_hrs: ' + str(offset_hrs))
		
		posts = getPosts(offset_hrs)
			
		idx = int(start_idx)
		
		logging.debug("memcache idx: " + str(idx))	
		template_values = {
			'posts': posts[idx:idx+10]
		}

		path = os.path.join(os.path.dirname(__file__), 'singlepost.html')
		self.response.out.write(template.render(path, template_values))
		
class deletePosts(webapp2.RequestHandler):
	def get(self, offset=0):
		logging.debug('deleting posts for day with offset:' + str(offset))
		offset_hrs = int(offset) + 5 #offset utc time
		current_date = datetime.datetime.now() 
		offset = datetime.timedelta(hours=offset_hrs) 
		max_date = current_date - offset
		dt = max_date.strftime("%Y-%m-%d")
		logging.debug( 'current_dt: ' + str(current_date) + ' offset: ' + str(offset_hrs) + ' max_date: ' + str(max_date) + 'dt: ' + dt)
		response = memcache.delete(dt)
		self.response.out.write('0-network failure, 1-not found, 2-success')
		self.response.out.write('deletePosts response: ' + str(response))

class MainUI(webapp2.RequestHandler):
	def get(self):
		logging.getLogger().setLevel(logging.DEBUG)
		logging.debug("in mainui")	
		
		posts = getPosts()
		template_values = {
			'posts': posts[0:10],
			'quote': getQuote()
		}
		
		path = os.path.join(os.path.dirname(__file__), 'topposts.html')
		self.response.out.write(template.render(path, template_values))

def getPosts(offset=0):
	offset_hrs = int(offset) + 5 #offset utc time
	current_date = datetime.datetime.now() 
	offset = datetime.timedelta(hours=offset_hrs) 
	max_date = current_date - offset
	dt = max_date.strftime("%Y-%m-%d")
	logging.debug( 'current_dt: ' + str(current_date) + ' offset: ' + str(offset_hrs) + ' max_date: ' + str(max_date) + 'dt: ' + dt)
	
	posts = deserialize_entities( memcache.get( dt))
	if posts != None:
		logging.debug('posts found in memcache')
		return posts
	
	query = "SELECT * FROM Post WHERE current_ts > Date(:1)"
	
	if offset_hrs != 5:
		#if they are trying to return posts from other than today, we need to append the range
		past_date_offset = datetime.timedelta(hours=offset_hrs-24)
		min_date = current_date - past_date_offset
		mindt = min_date.strftime("%Y-%m-%d")
		logging.debug('getting posts for date range: mindt: ' + mindt)
		query += " and current_ts < date(:2)"
		logging.debug('query: ' + query)
		posts = db.GqlQuery(query, dt, mindt)
	else:
		logging.debug('query: ' + query)
		posts = db.GqlQuery(query, dt)
	
	allposts = []	
	for p in posts:
		#logging.debug('getPosts.allPosts: ' + p.url)
		p.feed = p.url.split('/')[2];
		allposts.append(p)
	
	allposts.sort(key=lambda post: int(post.t_count) + int(post.fb_count), reverse=True )

	logging.debug('Adding allPosts to memcache')
	if len(allposts) > 0:
		memcache.add(dt, serialize_entities(allposts),604800) #store in memcache for a week
	
	logging.debug('displayPosts: returning template_values: length=' + str(len(allposts)))	
	return allposts

def serialize_entities(models):
	if models is None:
		return None
	elif isinstance(models, db.Model):
		return db.model_to_protobuf(models).Encode()
	else:
		return [db.model_to_protobuf(x).Encode() for x in models]

def deserialize_entities(data):
	if data is None:
		return None
	elif isinstance(data,str):
		#single instance
		return db.model_from_protobuf(entity_pb.EntityProto(data))
	return [db.model_from_protobuf(entity_pb.EntityProto(x)) for x in data]
	
################################################
# Retrieve a new random quote from i heart qotes.
# then save it in memcache and set it to expire
# every 12hrs.
################################################
def getQuote():
	quote = memcache.get('quote')
	#logging.debug('quote from memcache: ' + str(quote))
	if quote == None or quote == 'None':
		try:
			logging.debug('invoking iheartquotes')
			url = 'http://www.iheartquotes.com/api/v1/random?source=news&format=json'
			data = urllib2.urlopen(url, timeout=30).read()
			
			jsondata = simplejson.loads(data)
			quote = jsondata['quote']
			#logging.debug('quote being saved to memcache: ' + quote)
			memcache.add(key='quote',value=quote,time=43200)
		except Exception, error:
			logging.error('error invoking i heart quotes: ' + str(error))
	return quote;
