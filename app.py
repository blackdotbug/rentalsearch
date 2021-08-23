from flask import Flask, render_template, redirect, request, jsonify, url_for, session
from flask_session import Session
from flask_pymongo import PyMongo
import datetime
from splinter import Browser
from bs4 import BeautifulSoup
from time import sleep
import json
import requests
import re
import scrape_properties
from config import accessToken, SECRETKEY, MONGOURI, SESSTYPE, MONGODB, ENV
import sys
from webdriver_manager.chrome import ChromeDriverManager

executable_path = {'executable_path': ChromeDriverManager().install()}
sys.setrecursionlimit(8000)
app = Flask(__name__)
app.config.from_object(__name__)
app.config['SECRET_KEY'] = SECRETKEY
app.config['MONGO_URI'] = MONGOURI
app.config['SESSION_TYPE'] = SESSTYPE
app.config['SESSION_MONGODB_DB'] = MONGODB
app.config['FLASK_ENV'] = ENV
mongo = PyMongo(app)
Session(app)

@app.route("/")
def index():
    scrapes = list(mongo.db.scrape_log.find())
    scrapes = sorted(scrapes, key = lambda i: i['stamp'],reverse=True)
    for scrape in scrapes:
        scrape['stamp'] = scrape['stamp'].strftime("%b %d %Y %H:%M:%S")
    rentals = list(mongo.db.rentals.find())
    for rental in rentals:
        rental['value'] = -99
        if rental['rent'] and rental['sqft'] and type(rental['sqft']) == int:
            rental['value'] = round(int(''.join(i for i in rental['rent'] if i.isdigit()))/rental['sqft'],2)
        elif rental['rent'] and rental['sqft']:
            rental['value'] = round(int(''.join(i for i in rental['rent'] if i.isdigit()))/int(''.join(i for i in rental['sqft'] if i.isdigit())),2)

    if not session.get("compare") is None:
        session.pop("compare", None)
    if not session.get("calculate") is None:
        session.pop("calculate", None)
    return render_template("index.html", rentals=rentals, scrapes=scrapes)

@app.route("/scrape")
def scrape():
    rentals = mongo.db.rentals
    scrapes = mongo.db.scrape_log
    now = datetime.datetime.now()
    rental_data,scrape_stats = scrape_properties.scrape_all(executable_path)
    for address, rental in rental_data.items():
        if rental['address']:
            current = rentals.find_one({"address":address})
            if current and 'user_update' in current.keys():
                rental['user_update'] = current['user_update']
            if current and rental['sqft'] == '' and type(current['sqft']) == int:
                rental['sqft'] = current['sqft']
            if current and 'adjrent' in current.keys():
                rental['adjrent'] = current['adjrent']
            if current and 'movein' in current.keys():
                rental['movein'] = current['movein']
            if current and 'save' in current.keys() and current['save']:
                rental['save'] = current['save']
            rentals.replace_one({"address":address}, rental, upsert=True)
    for site, stat in scrape_stats.items():
        scrapes.replace_one({'site':site}, {'site': site, 'stat': stat, 'stamp': now}, upsert=True)
    return redirect("/", code=302)

@app.route("/scrape-one", methods=['GET', 'POST'])
def scrape_one():
    rentals = mongo.db.rentals
    scrapes = mongo.db.scrape_log
    now = datetime.datetime.now()
    link = request.args.get('url')
    rental_data, scrape_stats = scrape_properties.scrape_all(executable_path, link)
    for address, rental in rental_data.items():
        if rental['address']:
            current = rentals.find_one({"address":address})
            if current and 'user_update' in current.keys():
                rental['user_update'] = current['user_update']
            if current and rental['sqft'] == '' and type(current['sqft']) == int:
                rental['sqft'] = current['sqft']
            if current and 'adjrent' in current.keys():
                rental['adjrent'] = current['adjrent']
            if current and 'movein' in current.keys():
                rental['movein'] = current['movein']
            if current and 'save' in current.keys() and current['save']:
                rental['save'] = current['save']
            rentals.replace_one({"address":address}, rental, upsert=True)
    for site, stat in scrape_stats.items():
        scrapes.replace_one({'site':site}, {'site': site, 'stat': stat, 'stamp': now}, upsert=True)
    return redirect("/", code=302)

@app.route("/remove-scrape", methods=['GET', 'POST'])
def remove_scrape():
    link = request.args.get('url')
    mongo.db.scrape_log.delete_one({'site':link})
    return redirect("/", code=302)

@app.route("/calculate", methods=['GET', 'POST'])
def calculate():
    if not session.get("calculate") is None:
        rentals = session.get("calculate")
    else:
        links = request.form.getlist('update[]')
        numbers = scrape_numbers(links)
        rentals = list(mongo.db.rentals.find({'link': {'$in': links}}, {'_id': False}))
        for url,numbers_list in numbers.items():
            for rental in rentals:
                if rental['link'] == url:
                    rental['numbers'] = numbers_list
        session['calculate'] = rentals
        session.modified == True
    # print(rentals)
    return render_template("calculate.html", calculate=rentals)

def scrape_numbers(rental_urls):
    browser = Browser("chrome", **executable_path, headless=True)
    listings_numbers = {}
    for url in rental_urls:
        browser.visit(url)
        html = browser.html
        soup = BeautifulSoup(html, "html.parser")
        numbers = []
        deleted = []
        keywords = ['deposit','fee','pet rent']
        text = ["The page you are looking for can not be found","Sorry, the listing you are trying to access is no longer available.","We're sorry, but this listing is no longer on the market."]
        for tag in soup.descendants:
            if tag.string and any(sorry in tag.string for sorry in text):
                delete_listing(url)
                deleted.append(url)
                break
            else:
                if tag.string and '/>' not in tag.string and 'rtCommonProps' not in tag.string:
                    for word in keywords:
                        if re.search(rf'\b{word}\b', tag.string, flags=re.IGNORECASE):
                            numbers.append(tag.string)
        deduped_numbers = list(set(numbers))
        for i,number in enumerate(deduped_numbers):
            styled_number = number
            for word in keywords:
                if re.search(rf'\b{word}\b', styled_number, flags=re.IGNORECASE):
                    styled_number = re.sub(rf'\b{word}\b', f'<b>{word}</b>', styled_number, flags=re.IGNORECASE)
            deduped_numbers[i] = styled_number.strip()
        listings_numbers[url] = deduped_numbers
    browser.quit()
    for listing in listings_numbers.keys():
        if listing in deleted:
            listings_numbers.pop(listing)
    return listings_numbers

@app.route("/compare", methods=['GET', 'POST'])
def compare():
    if not session.get("compare") is None:
        rentals = session.get("compare")
    else:
        links = request.form.getlist('update[]')
        details = scrape_details(links)
        rentals = list(mongo.db.rentals.find({'link': {'$in': links}}, {'_id': False}))
        for url,detail_list in details.items():
            for rental in rentals:
                if rental['link'] == url:
                    if rental['sqft'] and int(rental['sqft']) > 0:
                        rental['details'] = detail_list
                    else:
                        sqfts = list(set(get_sqft(rental['link'])))
                        rental['details'] = detail_list + sqfts
        for rental in rentals:
            rental['value'] = -99
            if rental['rent'] and rental['sqft'] and type(rental['sqft']) == int:
                rental['value'] = round(int(''.join(i for i in rental['rent'] if i.isdigit()))/rental['sqft'],2)
            elif rental['rent'] and rental['sqft']:
                rental['value'] = round(int(''.join(i for i in rental['rent'] if i.isdigit()))/int(''.join(i for i in rental['sqft'] if i.isdigit())),2)
        session['compare'] = rentals
        session.modified = True
    # print(rentals)
    return render_template("compare.html", compare=rentals, accesstoken=accessToken)

def delete_listing(url):
    mongo.db.rentals.delete_one({'link':url})

def get_sqft(url):
    browser = Browser("chrome", **executable_path, headless=True)
    browser.visit(url)
    html = browser.html
    browser.quit()
    soup = BeautifulSoup(html, "html.parser")
    sqfts = []
    text = ['sqft', 'sq. ft.', 'sq ft', 'square footage', 'sq.ft.']
    for tag in soup.descendants:
        if tag.string and '/>' not in tag.string and 'rtCommonProps' not in tag.string:
            for word in text:
                if re.search(rf'\b{word}\b', tag.string, flags=re.IGNORECASE):
                    sqfts.append(tag.string)
    return sqfts

def scrape_details(rental_urls):
    browser = Browser("chrome", **executable_path, headless=True)
    listings_details = {}
    for url in rental_urls:
        browser.visit(url)
        html = browser.html
        soup = BeautifulSoup(html, "html.parser")
        details = []
        deleted = []
        keywords = ['dishwasher', 'fireplace', 'garage', 'off-street parking', 'off street parking', 'shed', 'basement', 'storage', 'gas stove', 'gas oven', 'gas range', 'hookups', 'washer/dryer', 'W/D', 'washer', 'dryer', 'laundry', 'transit', 'bus', 'trimet', 'apartment', 'duplex', 'triplex', 'multiplex','single-family', 'single family', 'house', 'unit']
        text = ["page you are looking for can not be found","the listing you are trying to access is no longer available","this listing is no longer on the market"]
        for tag in soup.descendants:
            if tag.string and any(sorry in tag.string for sorry in text):
                delete_listing(url)
                deleted.append(url)
                break
            else:
                if tag.string and '/>' not in tag.string and 'rtCommonProps' not in tag.string:
                    for word in keywords:
                        if re.search(rf'\b{word}\b', tag.string, flags=re.IGNORECASE):
                            details.append(tag.string)
        deduped_details = list(set(details))
        for i,detail in enumerate(deduped_details):
            styled_detail = detail
            for word in keywords:
                if re.search(rf'\b{word}\b', styled_detail, flags=re.IGNORECASE):
                    styled_detail = re.sub(rf'\b{word}\b', f'<b>{word}</b>', styled_detail, flags=re.IGNORECASE)
            deduped_details[i] = styled_detail
        listings_details[url] = deduped_details
    browser.quit()
    for listing in listings_details.keys():
        if listing in deleted:
            listings_details.pop(listing)
    return listings_details

@app.route("/update", methods=['GET','POST'])
def update_properties():
    updates = request.form
    keys = ['parking', 'laundry', 'dishwasher', 'transit', 'gasoven', 'fireplace', 'type']
    user_updates = {}
    sqft = 0
    for value in updates:
        if value in keys:
            user_updates[value] = updates[value]
        elif value == 'sqft' and updates['sqft']:
            sqft = int(updates['sqft'])
    if sqft > 0:
        mongo.db.rentals.update_one({'address':updates['address']}, {'$set' : {'user_update': user_updates, 'sqft': sqft}})
    else:
        mongo.db.rentals.update_one({'address':updates['address']}, {'$set' : {'user_update': user_updates}})

    if not session.get("compare") is None:
        for listing in session['compare']:
            if listing['address'] == updates['address']:
                listing['user_update'] = user_updates
                if sqft:
                    listing['sqft'] = sqft
                session.modified = True
    return redirect(url_for("compare"), code=302)

@app.route("/clean")
def clean():
    browser = Browser("chrome", **executable_path, headless=False)
    rentals = list(mongo.db.rentals.find())
    deleted = 0
    for rental in rentals:
        if any(x in rental['address'].lower() for x in ['gresham','wilsonville','sherwood', 'beaverton', 'tigard', 'oswego', 'hillsboro', 'aloha', 'happy valley', 'forest grove'] ):
            delete_listing(rental['link'])
            deleted += 1
        else:
            if 'adjrent' in rental.keys() and rental['adjrent'] == 0:
                delete_listing(rental['link'])
                deleted += 1
            else:
                if any(b in rental['beds'] for b in ['1 bed', '1 bd']):
                    delete_listing(rental['link'])
                    deleted += 1
                else:
                    browser.visit(rental['link'])
                    text = ["The page you are looking for can not be found","the listing you are trying to access is no longer available","this listing is no longer on the market"]
                    for t in text:
                        present = browser.is_text_present(t, wait_time=1)
                        if present == True:
                            delete_listing(rental['link'])
                            deleted += 1
                            break
    print(f"{deleted} deleted")
    browser.quit()
    return redirect("/", code=302)

@app.route("/saved", methods=['GET', 'POST'])
def saved_properties():
    updates = request.form
    addresses = updates.getlist("address")
    adjrents = updates.getlist("adjrent")
    moveins = updates.getlist("movein")
    saved = updates.getlist("saved")
    for i,address in enumerate(addresses):
        save = False
        if str(i+1) in saved:
            save = True
        mongo.db.rentals.update_one({'address':address}, {'$set' : {'adjrent': adjrents[i], 'movein': moveins[i], 'save': save}})
    return redirect("/", code=302)

@app.route("/toggle", methods=['GET', 'POST'])
def toggle_save():
    links = request.form.getlist('update[]')
    for url in links:
        current = mongo.db.rentals.find_one({"link":url})
        if 'save' in current.keys():
            if current['save']:
                saved = False
            else:
                saved = True
        else:
            saved = True
        mongo.db.rentals.update_one({'link':url}, {'$set' : {'save': saved}})
    return redirect("/", code=302)

@app.route("/delete", methods=['GET', 'POST'])
def delete_many():
    links = request.form.getlist('update[]')
    for url in links:
        delete_listing(url)
    return redirect("/", code=302)


if __name__ == "__main__":
    app.run(debug=True)
