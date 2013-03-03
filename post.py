class Post(db.Model):
	feed = db.StringProperty()
	url = db.StringProperty()
	title = db.StringProperty()
	fb_count = db.IntegerProperty()
	t_count = db.IntegerProperty()
	current_ts = db.DateTimeProperty(auto_now_add=True)
