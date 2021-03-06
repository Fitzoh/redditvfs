#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
This is a demo/proof of concept for the reddit virtual filesystem
quick-and-dirty
"""
import errno
import fuse
import stat
import time
import praw
import getpass
import ConfigParser
import sys
import urllib2
import format

fuse.fuse_python_api = (0, 2)


def sanitize_filepath(path):
    """
    Converts provided path to legal UNIX filepaths.
    """
    # '/' is illegal
    path = path.replace('/', '_')
    # Direntry() doesn't seem to like non-ascii
    path = path.encode('ascii', 'ignore')
    return path


class redditvfs(fuse.Fuse):
    def __init__(self, reddit=None, username=None, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)

        if reddit is None:
            raise Exception('reddit must be set')

    def mkdir(self, path, mode):
        if len(path.split('/')) == 3:
            #if we're trying to mkdir in the subreddit
            if path.split('/')[-1:][0][-4:] == '.sub':
                #and it's a .sub file
                if reddit.is_logged_in:
                    print("We want to sub to:" + path.split('/')[-1:][0][:-4])
                    reddit.subscribe(path.split('/')[-1:][0][:-4])
                    return
                else:
                    return -errno.ENOSYS
            else:
                return -errno.ENOSYS
        else:
            return -errno.ENOSYS

    def getattr(self, path):
        """
        returns stat info for file, such as permissions and access times.
        """
        print "getattr: "  + path
        # default nlink and time info
        st = fuse.Stat()
        st.st_nlink = 2
        st.st_atime = int(time.time())
        st.st_mtime = st.st_atime
        st.st_ctime = st.st_atime

        path_split = path.split('/')
        path_len = len(path_split)
        # set if filetype and permissions
        if path_split[-1] == '.' or path_split[-1] == '..':
            # . and ..
            st.st_mode = stat.S_IFDIR | 0444
        elif path in ['/', '/u', '/r']:
            # top-level directories
            st.st_mode = stat.S_IFDIR | 0444
        elif path_split[1] == 'r' and path_len == 3:
            # r/*/ - subreddits
            if reddit.is_logged_in():
                if path.split('/')[-1:][0][-4:] == '.sub':
                    my_subs = [sub.display_name.lower() for sub in reddit.get_my_subreddits()]
                    print my_subs
                    if (path.split('/')[-1:][0][:-4]).lower() not in my_subs:
                        print 'NOT FOUND'
                        st = -2
                    else:
                        st.st_mode = stat.S_IFDIR | 0444
            else:
                st.st_mode = stat.S_IFDIR | 0444
        elif path_split[1] == 'r' and path_len == 4:
            # r/*/* - submissions
            st.st_mode = stat.S_IFDIR | 0444
        elif (path_split[1] == 'r' and path_len == 4 and path_split[-1] in
                ['thumbnail', 'flat', 'votes', 'content']):
            # content stuff in submission
            st.st_mode = stat.S_IFREG | 0444
            post = get_comment_obj(path)
            if path_split[-1] == 'content':
                # TODO
                formatted = ''
            elif path_split[-1] == 'votes':
                # TODO votes information
                formatted = ''
            elif path_split[-1] == 'flat':
                # TODO votes information
                formatted = ''
            elif (path_split[-1] == 'thumbnail' and post.thumbnail != '' and
                    post.thumbnail != 'self'):
                f = urllib2.urlopen(post.thumbnail)
                if f.getcode() == 200:
                    formatted = f.read()
            st.st_size = len(formatted)
        elif (path_split[1] == 'r' and path_len > 4 and path_split[-1] not in
                ['thumbnail', 'flat', 'votes', 'content']):
            # comment post
            st.st_mode = stat.S_IFDIR | 0444
        elif (path_split[1] == 'r' and path_len > 4 and path_split[-1] in
                ['thumbnail', 'flat', 'votes', 'content']):
            # content stuff in comment post
            st.st_mode = stat.S_IFREG | 0444
            post = get_comment_obj(path)
            if path_split[-1] == 'content':
                # TODO
                formatted = ''
            elif path_split[-1] == 'votes':
                # TODO votes information
                formatted = ''
            elif path_split[-1] == 'flat':
                # TODO votes information
                formatted = ''
            st.st_size = len(formatted)
        else:
            # everything else is a file
            st.st_mode = stat.S_IFREG | 0444
        return st

    def readdir(self, path, offset):
        """
        returns a list of directories in requested path
        """

        # Every directory has '.' and '..'
        yield fuse.Direntry('.')
        yield fuse.Direntry('..')

        # TODO: maybe make this configurable later
        # cut-off length on items with id to make things usable for end-user
        pathmax = 50

        path_split = path.split('/')
        path_len = len(path_split)

        if path == '/':
            # top-level directory
            yield fuse.Direntry('u')
            yield fuse.Direntry('r')
        elif path_split[1] == 'r':
            if path_len == 2:
                # if user is logged in, populate with get_my_subreddits
                # otherwise, default to frontpage
                # TODO: figure out how to get non-logged-in default subreddits,
                # falling back to get_popular_subreddits
                if reddit.is_logged_in():
                    for subreddit in reddit.get_my_subreddits():
                        dirname = sanitize_filepath(subreddit.url.split('/')[2])
                        yield fuse.Direntry(dirname)
                else:
                    for subreddit in reddit.get_popular_subreddits():
                        dirname = sanitize_filepath(subreddit.url.split('/')[2])
                        yield fuse.Direntry(dirname)
            elif path_len == 3:
                # posts in subreddits
                subreddit = path_split[2]
                # TODO: maybe not hardcode limit?
                for post in reddit.get_subreddit(subreddit).get_hot(limit=20):
                    filename = sanitize_filepath(post.title[0:pathmax]
                            + ' ' + post.id)
                    yield fuse.Direntry(filename)
            elif path_len == 4:
                # a submission in a subreddit

                yield fuse.Direntry('flat')
                yield fuse.Direntry('votes')
                yield fuse.Direntry('content')

                post_id = path_split[3].split(' ')[-1]
                post = reddit.get_submission(submission_id = post_id)

                if post.thumbnail != "" and post.thumbnail != 'self':
                    # there is a thumbnail
                    yield fuse.Direntry('thumbnail')

                for comment in post.comments:
                    if 'body' in dir(comment):
                        yield fuse.Direntry(
                                sanitize_filepath(comment.body[0:pathmax]
                                    + ' ' + comment.id))
            elif len(path.split('/')) > 4:
                # a comment

                # Can't find a good way to get a comment from an id, but there
                # is a good way to get a submission from the id and to walk
                # down the tree, so doing that as a work-around.

                yield fuse.Direntry('flat')
                yield fuse.Direntry('votes')
                yield fuse.Direntry('content')

                comment = get_comment_obj(path)

                for reply in comment.replies:
                    if 'body' in dir(reply):
                        yield fuse.Direntry(
                                sanitize_filepath(reply.body[0:pathmax]
                                    + ' ' + reply.id))
        elif path_split[1] == 'u':
            if path_len == 2:
                # if user is logged in, show the user.  Otherwise, this empty
                # doesn't have any values listed.
                if reddit.is_logged_in():
                    yield fuse.Direntry(username)

    def read(self, path, size, offset, fh=None):
        path_split = path.split('/')
        path_len = len(path_split)

        if path_split[1] == 'r' and path_len >= 4:
            # Get the post or comment
            post_id = path_split[-2].split(' ')[-1]
            post = reddit.get_submission(submission_id=post_id)

            formatted = ''
            if path_split[-1] == 'content':
                formatted = format.format_sub_content(post)
                formatted = formatted.encode('ascii', 'ignore')
            elif path_split[-1] == 'votes':
                formatted = str(post.score) + '\n'
            elif path_split[-1] == 'flat':
                formatted = format.format_submission(post)
                formatted = formatted.encode('ascii', 'ignore')
            elif path_split[-1] == 'thumbnail' and post.thumbnail != '' and \
                    post.thumbnail != 'self':
                f = urllib2.urlopen(post.thumbnail)
                if f.getcode() == 200:
                    formatted = f.read
            return formatted[offset:offset+size]
        if path.split('/')[1] == 'u':
            # TODO user handling
            pass

        return -errno.ENOSYS

def get_comment_obj(path):
    """
    given a filesystem path, returns a praw comment object
    """
    # Can't find a good way to get a comment from an id, but there
    # is a good way to get a submission from the id and to walk
    # down the tree, so doing that as a work-around.
    path_split = path.split('/')
    path_len = len(path_split)
    post_id = path_split[3].split(' ')[-1]
    post = reddit.get_submission(submission_id = post_id)
    for comment in post.comments:
        if comment.id == path_split[4].split(' ')[-1]:
            break
    level = 4
    while level < path_len - 1:
        level += 1
        for comment in comment.replies:
            if comment.id == path_split[level].split(' ')[-1]:
                break
    return comment

def login_get_username(config):
    """
    returns the username of the user to login
    """
    try:
        username = config.get('login', 'username')
    except Exception, e:
        # Prompt for username
        username = raw_input("Username: ")
        pass
    return username


def login_get_password(config):
    """
    returns the password of the user to login
    """
    try:
        password = config.get('login', 'password')
    except Exception, e:
        # Prompt for password
        password = getpass.getpass()
        pass
    return password


if __name__ == '__main__':
    # Create a reddit object from praw
    reddit = praw.Reddit(user_agent='redditvfs')

    # Login only if a configuration file is present
    if '-c' in sys.argv:
        # Remove '-c' from sys.argv
        sys.argv.remove('-c')

        # User wants to use the config file, create the parser
        config = ConfigParser.RawConfigParser(allow_no_value=True)

        # Check for default login
        try:
            config.read('~/.redditvfs.conf')
        except Exception, e:
            pass
        finally:
            username = login_get_username(config=config)
            password = login_get_password(config=config)
            try:
                reddit.login(username=username, password=password)
                print 'Logged in as: ' + username
            except Exception, e:
                print e
                print 'Failed to login'
    else:
        username = None

    fs = redditvfs(reddit=reddit, username=username)
    fs.parse(errex=1)
    fs.main()
