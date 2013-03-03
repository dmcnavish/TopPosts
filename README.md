TopPosts
========

TopPosts is a side project of mine that searches the web each night in order to fine the most popular posts. The logic to determine what is popular and what isn't is based on data from popular social networks. The idea for this project came to be when I realized that my Google Reader feeds were growing on a day to day basis but my time to read the feeds was not. This allows me to parse out the best news without wasting time on fluff posts.

To run the application locally, start Google App Engine and load the main directory. The posts that are displayed are pulled from the database and stored in memcache.  In order to execute the cron job that analyzes and inserts the posts, navigate to localhost:{port}/cron.  The url is currently blocked so that it cannot be run by anyone except the admin in production. In order to run it locally, removed the 'login: admin' line from the app.yaml file for the cron entry.

The application is currently running on Google App Engine at http://mynewsagg.appspot.com/topposts