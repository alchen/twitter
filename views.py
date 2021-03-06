import os
import re
import requests
from BeautifulSoup import BeautifulSoup
from twitter import app, twitter
from flask import render_template, session, redirect, flash, url_for, request
from flask import send_from_directory, jsonify, abort, make_response


@app.route('/favicon.ico')
def favicon_ico():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'img/favicon.ico', mimetype='image/x-icon')


@app.route('/favicon.png')
def favicon_png():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'img/favicon.png', mimetype='image/png')


def timeline_pagination(resp):
    since_id = max_id = 0
    if resp.status == 200:
        tweets = resp.data

        for tweet in tweets:
            if since_id is 0 or since_id < tweet['id']:
                since_id = tweet['id']
            if max_id is 0 or max_id > tweet['id']:
                max_id = tweet['id']
        max_id -= 1
    else:
        tweets = []

        flash('Unable to load tweets from Twitter.')
        if 'errors' in resp.data:
            for error in resp.data['errors']:
                flash(error['message'])

    return (since_id, max_id, tweets)


@app.route('/')
def show_index():
    if not get_twitter_token():
        return render_template('prompt.html')

    if 'max_id' in request.args:
        resp = twitter.get('statuses/home_timeline.json',
                           data={'max_id': request.args['max_id']})
    else:
        resp = twitter.get('statuses/home_timeline.json')

    if request.is_xhr:
        if resp.status == 401:
            return jsonify(success=False, data='Unauthorized account access.')

        since_id, max_id, tweets = timeline_pagination(resp)

        return jsonify(success=True, data=render_template('_timeline.html',
                       tweets=tweets, max_id=max_id, since_id=since_id,
                       endpoint='show_index', endpoint_args={}))
    else:
        if resp.status == 401:
            session.pop('twitter_token')
            flash('Unauthorized account access.')
            return render_template('prompt.html')

        since_id, max_id, tweets = timeline_pagination(resp)

        return render_template('timeline.html', tweets=tweets, max_id=max_id,
                               since_id=since_id, endpoint="show_index",
                               endpoint_args={})


@app.route('/~mentions')
def show_mentions():
    if not get_twitter_token():
        return redirect(url_for('show_index'))

    if 'max_id' in request.args:
        resp = twitter.get('statuses/mentions_timeline.json',
                           data={'max_id': request.args['max_id']})
    else:
        resp = twitter.get('statuses/mentions_timeline.json')

    if request.is_xhr:
        if resp.status == 401:
            return jsonify(success=False, data='Unauthorized account access.')

        since_id, max_id, tweets = timeline_pagination(resp)

        return jsonify(success=True, data=render_template('_timeline.html',
                       tweets=tweets, max_id=max_id, since_id=since_id,
                       endpoint='show_mentions', endpoint_args={}))
    else:
        if resp.status == 401:
            session.pop('twitter_token')
            flash('Unauthorized account access.')
            return redirect(url_for('show_index'))

        since_id, max_id, tweets = timeline_pagination(resp)

        return render_template('timeline.html', tweets=tweets, max_id=max_id,
                               since_id=since_id, endpoint="show_mentions",
                               endpoint_args={})


@app.route('/~messages')
def show_messages():
    token = get_twitter_token()
    if not token:
        return redirect(url_for('show_index'))

    resp = twitter.get('direct_messages.json')
    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status == 200:
        messages = resp.data
    else:
        messages = []
        flash('Unable to load tweets from Twitter. Maybe out of '
              'API calls or Twitter is overloaded.')

    return render_template('messages.html', messages=messages)


@app.route('/@<name>')
@app.route('/<name>')
def show_user(name):
    if not get_twitter_token():
        return redirect(url_for('show_index'))

    resp = twitter.get('users/show.json', data={'screen_name': name})

    if resp.status == 401:
        flash('Unauthorized account access, or blocked account.')
        return redirect(url_for('show_index'))

    profile = resp.data

    if 'max_id' in request.args:
        resp = twitter.get('statuses/user_timeline.json',
                           data={'max_id': request.args['max_id'],
                                 'screen_name': name})
    else:
        resp = twitter.get('statuses/user_timeline.json',
                           data={'screen_name': name})

    if request.is_xhr:
        if resp.status == 401:
            return jsonify(success=False, data='Unauthorized account access.')

        since_id, max_id, tweets = timeline_pagination(resp)

        return jsonify(success=True, data=render_template('_timeline.html',
                       tweets=tweets, max_id=max_id, since_id=since_id,
                       endpoint='show_user', endpoint_args={'name': name}))
    else:
        if resp.status == 401:
            flash('The user is protected, or you are blocked.')

        since_id, max_id, tweets = timeline_pagination(resp)

        return render_template('profile.html', tweets=tweets, max_id=max_id,
                               since_id=since_id, endpoint="show_user",
                               endpoint_args={'name': name}, profile=profile)


@app.route('/+update', methods=['GET', 'POST'])
def update():
    resp = twitter.post('statuses/update.json', data={
        'status': request.form['status'],
        'in_reply_to_status_id': request.form['in_reply_to']
    })

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully tweeted your new status')

    return redirect(url_for('show_index'))


@app.route('/-update/<int:id>')
def unupdate(id):
    resp = twitter.post('statuses/destroy/%d.json' % id)

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully deleted your new tweet')

    return redirect(url_for('show_index'))


@app.route('/+retweet/<int:id>')
def retweet(id):
    resp = twitter.post('statuses/retweet/%d.json' % id)

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully retweeted.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/-retweet/<int:id>')
def unretweet(id):
    resp = twitter.get('statuses/show/%d.json?include_my_retweet=1' % id)

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        retweet_id = resp.data['current_user_retweet']['id']
        resp = twitter.post('statuses/destroy/%d.json' % retweet_id)
        if resp.status == 200:
            flash('Successfully unretweeted.')
        else:
            flash('Unretweet failed.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/+favorite/<int:id>')
def favorite(id):
    resp = twitter.post('favorites/create.json', data={'id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully favorited.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/-favorite/<int:id>')
def unfavorite(id):
    resp = twitter.post('favorites/destroy.json', data={'id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully unfavorited.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/+follow/<int:id>')
def follow(id):
    resp = twitter.post('friendships/create.json', data={'user_id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully followed, or your request has been sent.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/-follow/<int:id>')
def unfollow(id):
    resp = twitter.post('friendships/destroy.json', data={'user_id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully unfollowed.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/+block/<int:id>')
def block(id):
    resp = twitter.post('blocks/create.json', data={'user_id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully blocked.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/-block/<int:id>')
def unblock(id):
    resp = twitter.post('blocks/destroy.json', data={'user_id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200:
        for error in resp.data['errors']:
            flash(error['message'])
    else:
        flash('Successfully unblocked.')

    return redirect(request.referrer or url_for('show_index'))


@app.route('/~thread/<int:id>')
def thread(id):
    resp = twitter.get('statuses/show.json', data={'id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status != 200 or not resp.data['in_reply_to_status_id']:
        tweet = None
    else:
        tweet = resp.data
        resp = twitter.get('statuses/show.json',
                           data={'id': tweet['in_reply_to_status_id']})
        if resp.status == 200:
            replied_tweet = resp.data
        else:
            replied_tweet = None

    if tweet is None or replied_tweet is None:
        flash('Unable to load tweets from Twitter. Maybe out of '
              'API calls or Twitter is overloaded.')

    return render_template('reply.html', id=id, tweet=tweet,
                           replied_tweet=replied_tweet)


@app.route('/+reply/<int:id>')
def reply(id):
    resp = twitter.get('statuses/show.json', data={'id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status == 200:
        tweet = resp.data
    else:
        tweet = None
        flash('Unable to load tweets from Twitter. Maybe out of '
              'API calls or Twitter is overloaded.')

    names = re.findall(r'(@\w+)', tweet['text'])
    author = '@' + tweet['user']['screen_name']
    user = '@' + session['twitter_user']
    if author in names:
        names.remove(author)
    if user in names:
        names.remove(user)
    tweet_prefix = ' '.join([author] + names) + ' '

    return render_template('reply.html', id=id, tweet=tweet,
                           tweet_prefix=tweet_prefix)


@app.route('/+quote/<int:id>')
def quote(id):
    resp = twitter.get('statuses/show.json', data={'id': id})

    if resp.status == 401:
        session.pop('twitter_token')
        flash('Unauthorized account access.')
        return redirect(url_for('show_index'))

    if resp.status == 200:
        tweet = resp.data
    else:
        tweet = None
        flash('Unable to load tweets from Twitter. Maybe out of '
              'API calls or Twitter is overloaded.')

    return render_template('quote.html', id=id, tweet=tweet)


def login_jail(login_page):
    soup = BeautifulSoup(login_page)
    form = soup.find('form', attrs={'id': 'oauth_form'})
    if form is not None:
        form['action'] = url_for('oauth_authorize')
    return str(soup)


@app.route('/login')
def login():
    if app.config['PROXY'] is True:
        redirect = twitter.authorize(
            callback=url_for(
                'oauth_authorized',
                next=request.args.get('next') or request.referrer or None
            )
        )
        resp = requests.get(redirect.location)
        if resp.status_code == 200:
            r = make_response(login_jail(resp.text))
            for n, v in resp.cookies.iteritems():
                r.set_cookie(n, v)
            return r
        else:
            flash('Failed to retrieve OAuth authorization page.')
            return redirect(url_for('show_index'))
    else:
        return twitter.authorize(
            callback=url_for(
                'oauth_authorized',
                next=request.args.get('next') or request.referrer or None
            )
        )


@app.route('/oauth/authorize', methods=['post'])
def oauth_authorize():
    if app.config['PROXY'] is True:
        payload = request.form.to_dict()
        resp = requests.post(
            twitter.authorize_url,
            params=payload,
            headers={
                'origin': 'https://api.twitter.com',
                'referer': payload['redirect_after_login']
            },
            cookies={
                '_twitter_sess': request.cookies.get('_twitter_sess'),
                'guest_id': request.cookies.get('guest_id'),
            }
        )
        return login_jail(resp.text)
    else:
        abort(404)


@app.route('/logout')
def logout():
    next_url = request.args.get('next') or url_for('show_index')
    session.pop('twitter_token')
    flash('You\'re signed out.')

    return redirect(next_url)


@twitter.tokengetter
def get_twitter_token(token=None):
    return session.get('twitter_token')


@app.route('/oauth-authorized')
@twitter.authorized_handler
def oauth_authorized(resp):
    next_url = request.args.get('next') or url_for('show_index')
    if resp is None:
        flash(u'You have been denied the request to sign in.')
        return redirect(next_url)

    session['twitter_token'] = (resp['oauth_token'],
                                resp['oauth_token_secret'])
    session['twitter_user'] = resp['screen_name']
    session['twitter_id'] = resp['user_id']

    icon = twitter.get('users/show.json?screen_name=%s' % resp['screen_name'])
    if icon.status == 200:
        session['twitter_name'] = icon.data['name']
        session['twitter_icon'] = icon.data['profile_image_url']

    return redirect(next_url)
