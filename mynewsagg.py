import traceback
import mainui
from google.appengine.ext import db
import json as simplejson
from google.appengine.api import taskqueue
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import mail
import logging
import time, datetime
import urllib2
from xml.dom import minidom
import smtplib
from email.mime.text import MIMEText
import email.Charset
email.Charset.add_charset('utf-8',email.Charset.SHORTEST,None, None)
import webapp2

DEBUG_LOGGING = True
TWITTER_COUNT_URL = 'http://urls.api.twitter.com/1/urls/count.json?url='

class MainPage(webapp2.RequestHandler):
	def get(self):
		logging.debug('request received')
		self.response.out.write("<html><body><p>")
		#aggregateNews()
		taskqueue.add(url='/worker')
		self.response.out.write('Worker added to queue')
		self.response.out.write("</p></body></html>")

class AggWorker(webapp2.RequestHandler):
	def post(self):
		try:
			logging.debug('starting worker')
			aggregateNews()
		except Exception as err:
			logging.error('Error: ' + str(err))

#######################
# used to load posts into db locally
#########################			
class TestPopulater(webapp2.RequestHandler):
	def get(self, offset_hr=24):
		testPosts = []
		curr_date = datetime.datetime.now()
		hours = datetime.timedelta(hours=int(offset_hr))
		ts = curr_date - hours
		#site = Site('www.google.com', 'title', 'www.google.com', 4, _content="test content")
		#self.response.out.write('single site: ' + str(site.feed))
		for n in range(20):
			self.response.out.write('<br/>creating post for :' + str(n))
			idx = str(n)
			testPosts.append(Site('http://feed.com/1023', 'title'+idx, 'http://abduzeedo.com/daily-inspiration-1023', n, _content="test content" + idx, _current_ts=ts))
		self.response.out.write('<br/>posts:' + str(testPosts))
		storePosts(testPosts)
		self.response.out.write('<br/>test posts created')

class Site:
	def __init__(self, _feed='', _title='',_url='', _t_count=0, _fb_total_count=0, _fb_share_count=0, _fb_like_count=0, _content='', _current_ts=None):
		self.feed = _feed
		self.title = _title
		self.url = _url
		self.t_count = int(_t_count)
		self.fb_share_count = int(_fb_share_count)
		self.fb_like_count = int(_fb_like_count)
		self.fb_total_count = int(_fb_total_count)
		self.content = _content
		self.current_ts = _current_ts
	
def log(str):
	if DEBUG_LOGGING:
		logging.debug(str)
		#print(str)		

###############################################
# build the url used to invoke the YQL api which 
# will return the given urls rss feed
###############################################
def buildYQLUrl(url):
	new_url = 'http://query.yahooapis.com/v1/public/yql?q=select%20*%20from%20feed%20where%20url="'
	new_url = new_url + url + '"'
	#log('new url: ' + new_url)
	return new_url

def buildYQLJsonUrl(url):
	new_url= 'http://query.yahooapis.com/v1/public/yql?q=select%20*%20from%20json%20where%20url="'
	new_url = new_url + url + '"&format=json'
	return new_url

###############################################
# iterate over each post in the feed url 
#and return all of the posts since the min time
###############################################
def getPost(orig_url, min_time):
	logging.debug("start: " + orig_url)
	posts = []
	
	url = buildYQLUrl(orig_url)
	
	response = urllib2.urlopen(url, timeout=60)
	##TODO: handle errors
	dom = minidom.parse(response)
	
	nodeField = 'item'
	
	if len(dom.getElementsByTagName('item')) == 0:
		nodeField = 'entry'	
	
	#this will parse xml feeds
	for node in dom.getElementsByTagName(nodeField):
		title =  getText(node.getElementsByTagName('title')[0].childNodes)
		#log('title: ' + title)
		pub_dt = getPublishedDate(node)
		if pub_dt == '' or not comparePubDate(pub_dt , min_time, nodeField):
			continue
		#log('title: ' + title)
		linkTag = 'feedburner:origLink'
		if len(node.getElementsByTagName(linkTag)) == 0:
			if len(node.getElementsByTagName('link')) != 0 and getText(node.getElementsByTagName('link')[0].childNodes) != '':
				linkTag = 'link'
			elif len(node.getElementsByTagName('link')) != 0 and node.getElementsByTagName('link')[0].getAttribute('href') != None:
				linkTag = 'link'
			else:
				linkTag = 'id'
		#log('linkTag: ' + linkTag)
		link = ''
		if linkTag == 'link' and node.getElementsByTagName('link')[0].getAttributeNode('href') != None:
			link = node.getElementsByTagName('link')[0].getAttributeNode('href').nodeValue
		else:
			link =  getText(node.getElementsByTagName(linkTag)[0].childNodes)
			link = formatLink(link)
		if skipSite(link) == True:
			log('skipping link: ' + link)
			continue
		count = getTwitterCount(link)
		content = getContentData(node)
		#log('adding url: ' + url)
		posts.append(Site(orig_url, title, link, count, _content=content))
	logging.debug("end: " + orig_url + " num posts: " + str(len(posts)))
	return posts
	
############################################################################
#Add all urls that we do not want added to the end list here.
############################################################################
def skipSite(url):
	if 'www.cnn.com/video' in url:
		return True;
	elif url == '':
		return True;
	return False;

######################################
# invoke twitter url to get the number
# of retweets for the given link
######################################
def getTwitterCount(url):
	try:
		tUrl = TWITTER_COUNT_URL + url
		f = urllib2.urlopen(tUrl, timeout=60)
		items = f.readline().strip().split(",")
		count = int(items[0].strip('{"count":'))
		#log('twitter count: ' + str(count))
	except Exception, error:
		logging.error('error getTwitterCount, setting count to 0 ' + url + ' :' + str(error))
		return 0
	return count


######################################
# parse the content out of the feed
# may need to remove any special chars
######################################
def getContentData(node):
	contentTagName = 'description'
	if len(node.getElementsByTagName(contentTagName)) == 0:
		if len(node.getElementsByTagName('content')) ==0:
			contentTagName = 'summary'
		else:
			contentTagName = 'content'
	content = getText(node.getElementsByTagName(contentTagName)[0].childNodes)
	return content

######################################
# published node is different for rss 
# and atom, this will get the date for 
# either.
####################################
def getPublishedDate(node):
	pubDateTagName = 'pubDate'

	if len(node.getElementsByTagName(pubDateTagName)) == 0:
		if len(node.getElementsByTagName('published')) == 0:
			if len(node.getElementsByTagName('updated')) == 0:
				return ''
			pubDateTagName = 'updated'
		else:
			pubDateTagName = 'published'
	
	nodeList = node.getElementsByTagName(pubDateTagName)[0].childNodes		
	return getText(nodeList)


###################################
# Some sites add extra chars onto their feeds which 
# throw off the counts, we need to strip the url of these chars
# so that we can get accorate counts
###################################
def formatLink(link):	
	newLink = link.rpartition('#')
	if newLink[0] != '':
		link = newLink[0]
	return link
	#newLink = link.rpartition('?')
	#log('link: ' + link + ' newLink: ' + newLink[0])
	#if newLink[0] == '':
	#	return link
	#return newLink[0]

####################################
# get the text from a dom element
####################################
def getText(nodeList):
	rc = []
	for node in nodeList:
		if node.nodeType == node.TEXT_NODE or node.nodeType == node.CDATA_SECTION_NODE:
			rc.append(node.data)
	return ''.join(rc)


#######################################################
# compare the published date to determine
# if it is new enough to view, we don't want old posts
#######################################################
def comparePubDate(pub_dt, min_time, nodeType):
	#log('pub_dt: ' + str(pub_dt))
	if nodeType == 'entry':
		fmt = "%Y-%m-%dT%H:%M:%S.%f"
		splitField = '-'
		if 'Z' in pub_dt:
			fmt = "%Y-%m-%dT%H:%M:%S"
			splitField = 'Z'
		split_dt = str(pub_dt).rpartition(splitField)
		tz = split_dt[2]
		#log('time zone: ' + split_dt[2])
		pub_datetime = datetime.datetime.fromtimestamp(time.mktime(time.strptime(split_dt[0], fmt)))
		pub_datetime = adjustTimezoneByNum(pub_datetime, tz)
	elif '+' in str(pub_dt):
		pub_datetime = datetime.datetime.fromtimestamp(time.mktime(time.strptime(str(pub_dt), "%a, %d %b %Y %H:%M:%S +0000")))
	else:
		fmt = "%a, %d %b %Y %H:%M:%S %Z"
		split_dt = str(pub_dt).rpartition(' ')
		tz = split_dt[2]
		pub_datetime = datetime.datetime.fromtimestamp(time.mktime(time.strptime(split_dt[0], "%a, %d %b %Y %H:%M:%S")))
		pub_datetime = adjustTimezoneByName(pub_datetime,tz)

	#log('pub_datetime: ' + str(pub_datetime))
	if ( min_time - pub_datetime) > datetime.timedelta(hours = 0):
		#log('pub_datetime is less than min_time, pub_datetime: ' + str(pub_datetime))
		return False
	return True

####################################
# adjust the datetime to match EST 
####################################
def adjustTimezoneByName(dt, tz):
	offset = 0
	if tz == 'PST':
		offset = 3
	elif tz == 'CST':
		offset = 2
	elif tz == 'GMT':
		offset = 5
	dt = dt + datetime.timedelta(hours=offset)
	return dt

####################################
# this needs to be revisited
####################################
def adjustTimezoneByNum(dt, tz):
	offset = -5
	try:
		#if timezone is blank then assume UTC 
		if tz == '':
			offset = -5
		elif (tz.rpartition(':')[0]).isdigit() == False:
			offset = -5
		else:
			offset = int(tz.rpartition(':')[0]) * -1
		
		if offset == -8:
			offset = -5
	except Exception, error:
		logging.error('error adjustTimezoneByNum' + str(error))
	dt = dt + datetime.timedelta(hours=offset)
	return dt

####################################
# Retreive the minimum post time of 
# a post that can be included
####################################
def getMinTime():
	#minDate = 'Sat, 11 Nov 2011 14:00:00 PST'
	curr_date = datetime.datetime.now()
	log('curr_date: ' + str(curr_date))	
	hours = datetime.timedelta(hours=17)
	prev_time = curr_date - hours
	log('prev_time: ' + str(prev_time))
	return prev_time


####################################
# Invoke facebook FQL api to get 
# likes/shares for each url
####################################
def retreiveFBStats(sites):
	logging.debug('retreiveFBStats start')
	url = 'http://api.facebook.com/method/fql.query?query=select%20%20url,click_count,like_count,%20share_count,total_count%20from%20link_stat%20where%20url%20IN%20("'
	url = url + '","'.join([str(x.url) for x in sites if hasattr(x, 'url')]) + '")' 
	logging.debug('url: ' + url)
	response = minidom.parse(urllib2.urlopen(url, timeout=60))
	logging.debug('FB response success')
	
	if  response.getElementsByTagName('link_stat') == None:
		logging.debug('returning link_stat = None')
		return sites
	elif len(response.getElementsByTagName('link_stat')) <= 0:
		logging.debug('returning link_stat len <=0')
		return sites

	for node in response.getElementsByTagName('link_stat'):
		if len(node.getElementsByTagName('url')) <= 0:
			logging.debug('skipping element because url is null')
			continue
		site = getText(node.getElementsByTagName('url')[0].childNodes)
		total_count = getText(node.getElementsByTagName('total_count')[0].childNodes)
		share_count = getText(node.getElementsByTagName('share_count')[0].childNodes)
		like_count = getText(node.getElementsByTagName('like_count')[0].childNodes)
		#log(site + ' ' + str(total_count))
		for s in (s for s in sites if s.url == site):
			s.fb_total_count = total_count	
			s.fb_share_count = share_count
			s.fb_like_count = like_count
			break

	return sites

####################################
# sort the list in order of their twitter and fb count
####################################
def sortSites(sites):
	logging.debug('remove null and blank entries')
	for s in sites[:]:
		if s == None or s == [] or not hasattr(s,'t_count'): sites.remove(s)

	logging.debug('sorting sites')
	sites.sort(key=lambda site: int(site.t_count) + int(site.fb_share_count), reverse=True )

########################################################################
# since some sites post multiple times a day and are out weighing other 
# sites, each site is only allowed to have one post show up in the final
# list
########################################################################
def removeDups(sites):
	unique_sites = []
	unique_names = []
	for s in sites:
		if s.feed not in unique_names:
			unique_names.append(s.feed)
			unique_sites.append(s)
	return unique_sites


########################################################################
# read in any redit sites and parse out the first few posts and
# then check their fb/twitter count
########################################################################
def getRedditData(orig_url, retry=0):
	posts = []
	logging.debug(orig_url + ' retry: ' + str(retry))
	if retry >= 3:
		return None 
	else:
		try:
			if retry > 0:
				time.sleep(31.0)
			log('invoking reddit')
			new_url = new_url = buildYQLJsonUrl(orig_url)
			data = urllib2.urlopen(new_url, timeout=60).read()
			jsondata = simplejson.loads(data)
			#since there are so many, lets just pull out the first 5
			i = 0
			rmax = 5
			while i < rmax and rmax < 50 and i < len(jsondata['query']['results']['json']['data']['children']):
				title = jsondata['query']['results']['json']['data']['children'][i]['data']['title']
				url = jsondata['query']['results']['json']['data']['children'][i]['data']['url']
				url = formatLink(url)
				#skip youtube videos
				if 'www.youtube.com' in url:
					rmax+=1
					continue
				t_count = getTwitterCount(url)
				
				postExists = False
				for p in posts:
					if title not in p.title:	
						postExists = True
						break
				if postExists == False:
					posts.append(Site(orig_url, title, url, t_count))
				else:
					rmax+=1
					
				i+= 1
			logging.debug("max: " + str(rmax))
			return posts
		except Exception, error:
			logging.error('error invoking redit: ' + str(error))
			return getRedditData(orig_url, retry+1)

########################################################################
# read in any redit sites
########################################################################
def addRedit():
	posts = []
	sites = open('redit.in')
	for orig_url in sites.read().splitlines():
		log('redit url: ' + orig_url)
		#new_url = buildYQLJsonUrl(orig_url)
		site_posts = getRedditData(orig_url)
		if site_posts != None and len(site_posts) > 0:
			#log("reddit posts: " + str(site_posts))
			posts.extend( site_posts )
		else:
			logging.debug("no reddit posts found for url")
	return posts

########################################################################
# read in any digg sites
# TODO: combine with above reddit method
########################################################################	
def addDigg():
	posts = []
	sites = open('digg.in')
	for orig_url in sites.read().splitlines():
		log('digg url: ' + orig_url)
		#new_url = buildYQLJsonUrl(orig_url)
		site_posts = getDiggData(orig_url)
		if site_posts != None and len(site_posts) > 0:
			#log("reddit posts: " + str(site_posts))
			posts.extend( site_posts )
		else:
			logging.debug("no digg posts found for url")
	return posts
	
########################################################################
# read in any digg sites and parse out the first few posts and
# then check their fb/twitter count
########################################################################
def getDiggData(new_url):
	posts = []
	try:
		log('invoking digg')
		data = urllib2.urlopen(new_url, timeout=60).read()
		jsondata = simplejson.loads(data)
		#since there are so many, lets just pull out the first 5
		i = 0
		rmax = 5
		while i < rmax and i < len(jsondata['stories']):
			title = jsondata['stories'][i]['title']
			url = jsondata['stories'][i]['url']
			url = formatLink(url)
			t_count = getTwitterCount(url)
			
			postExists = False
			for p in posts:
				if title not in p.title:	
					postExists = True
					break
			if postExists == False:
				posts.append(Site(new_url, title, url, t_count))
			else:
				rmax+=1
			
			#posts.append(Site(new_url, title, url, t_count))
			i+= 1
		return posts
	except Exception, error:
		logging.error('error invoking digg: ' + str(error))
		#return getRedditData(orig_url, retry+1)	


########################################################################
# Iterate over the posts and create a single string, then email it
########################################################################
def emailTopPosts(posts):
	msg_txt = '<br/>'.join( ('<a href="'+ p.url +'">' + p.title + '</a>' + ' twitter: ' + str(p.t_count) + ' fb shares: ' + str(p.fb_share_count) ) for p in posts)
	#log('emailing posts: ' + msg_txt)
	from_addr = 'dave8051@gmail.com'
	to_addr = ['dave8051@gmail.com']	
	
	msg = MIMEText(msg_txt.encode('iso-8859-15','replace'),'html',_charset='iso-8859-15')
	
	msg['Subject'] = "Today's Top News"
	msg['To'] = ','.join(to_addr)
	msg['From'] = from_addr
	log('sending email')
	
	mail.send_mail(sender=from_addr, to= ','.join(to_addr), subject="Today's Top News", body=msg_txt, html=msg_txt)
	log('email sent')

########################################
# Object that will be stored in the db
########################################
class Post(db.Model):
	feed = db.StringProperty()
	url = db.StringProperty(multiline=True)
	title = db.StringProperty(multiline=True)
	fb_count = db.IntegerProperty()
	t_count = db.IntegerProperty()
	current_ts = db.DateTimeProperty(auto_now_add=True)
	content = db.TextProperty()


########################################
# Store the posts in the db
########################################
def storePosts(posts):
	log('storing posts')
	for p in posts:
		post = Post()
		post.url = p.url
		post.feed = p.feed
		post.title = p.title
		post.fb_count = int(p.fb_share_count)
		post.t_count = int(p.t_count)
		post.content = p.content	
		if p.current_ts != None:
			post.current_ts = p.current_ts
		post.put()

def aggregateNews():
	min_time = getMinTime()

	posts = []
	sites = open('sites.in')
	
	for url in sites.read().splitlines():
		try:
			log('feed url: ' + url)
			posts.extend( getPost(url, min_time))
		except Exception, error:
			logging.error('error getPost(): ' + str(error))

	#add any redit posts to the list
	posts.extend(addRedit())	
	#add any digg posts
	posts.extend(addDigg())
	
	start = 0
	stop = 10
	allposts = posts
	posts = []

	try:	
		while start < len(allposts):
			posts.extend( retreiveFBStats(allposts[start:stop]) )
			stop+=10
			start+=10
	except Exception, error:
		logging.error('error processing retrieveFBStats' + str(error))
	
	sortSites(posts)

	#log( 'posts within range: ')
	#for p in posts:
	#	log( p.url + ' t_count: ' + str(p.t_count) +  ' fb_count: ' + str(p.fb_total_count) + ' fb_share: ' + str(p.fb_share_count) + ' fb_like: ' + str(p.fb_like_count) + ' total: ' + str( int(p.t_count) + int(p.fb_share_count)))

	unique_posts = removeDups(posts)

	log( 'unique posts: ' )
	for u in unique_posts:
		log( u.url )
	
	#emailTopPosts( unique_posts[0:10])

	storePosts(unique_posts)
	

logging.getLogger().setLevel(logging.DEBUG)
app = webapp2.WSGIApplication([('/cron', MainPage), ('/worker', AggWorker), ('/topposts', mainui.MainUI), webapp2.Route('/testPosts/<offset_hr:\w+>', TestPopulater), webapp2.Route('/displayposts/<start_idx:\w+>/<offset_hrs:\w+>', mainui.displayPosts), webapp2.Route('/deleteposts/<offset:\w+>', mainui.deletePosts)], debug=True)

def main():
	run_wsgi_app(app)

if __name__ == '__main__':
	main()
