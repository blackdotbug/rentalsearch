from flask import Flask, render_template, redirect, request, jsonify
from flask_pymongo import PyMongo
import datetime
from splinter import Browser
from bs4 import BeautifulSoup
from time import sleep
import json 
import requests
import re
import scrape_properties

app = Flask(__name__)

# Use flask_pymongo to set up mongo connection
app.config["MONGO_URI"] = "mongodb://localhost:27017/rental_search"
mongo = PyMongo(app)

@app.route("/")
def index():
    scrapes = list(mongo.db.scrape_log.find())
    scrapes = sorted(scrapes, key = lambda i: i['stamp'],reverse=True)
    for scrape in scrapes:
        scrape['stamp'] = scrape['stamp'].strftime("%b %d %Y %H:%M:%S")
    rentals = list(mongo.db.rentals.find())
    for rental in rentals:
        rental['value'] = -99
        if rental['rent'] and rental['sqft']:
            rental['value'] = round(int(''.join(i for i in rental['rent'] if i.isdigit()))/int(''.join(i for i in rental['sqft'] if i.isdigit())),2)
    return render_template("index.html", rentals=rentals, scrapes=scrapes)

@app.route("/scrape")
def scrape():
    rentals = mongo.db.rentals
    scrapes = mongo.db.scrape_log
    now = datetime.datetime.now()
    rental_data,scrape_stats = scrape_properties.scrape_all()
    for address, rental in rental_data.items():
        if rental['address']:
            rentals.replace_one({"address":rental['address']}, rental, upsert=True)
    for site, stat in scrape_stats.items():
        scrapes.replace_one({'site':site}, {'site': site, 'stat': stat, 'stamp': now}, upsert=True)
    return redirect("/", code=302)

@app.route("/scrape-one", methods=['GET', 'POST'])
def scrape_one():
    rentals = mongo.db.rentals
    scrapes = mongo.db.scrape_log
    now = datetime.datetime.now()
    link = request.args.get('url')
    rental_data, scrape_stats = scrape_properties.scrape_all(link)
    for address, rental in rental_data.items():
        if rental['address']:
            rentals.replace_one({"address":rental['address']}, rental, upsert=True)
    for site, stat in scrape_stats.items():
        scrapes.replace_one({'site':site}, {'site': site, 'stat': stat, 'stamp': now}, upsert=True)
    return redirect("/", code=302)

@app.route("/map")
def map_all():
    data = mongo.db.rentals.find()
    rentals = []
    for row in data:
        if 'lat' in row.keys():
            rental = {'address': row['address'], 'lat':row['lat'], 'lng':row['lng']}
            rentals.append(rental)
    return render_template("map.html", rentals=rentals)

@app.route("/compare", methods=['GET', 'POST'])
def compare():
    links = request.form.getlist('compare[]')
    details = scrape_details(links)
    rentals = list(mongo.db.rentals.find({'link': {'$in': links}}))
    for url,detail_list in details.items():
        for rental in rentals:
            if rental['link'] == url:
                rental['details'] = detail_list
    return render_template("compare.html", compare=rentals)

def delete_listing(url):
    mongo.db.rentals.delete_one({'link':url})

def scrape_details(rental_urls):
    executable_path = {"executable_path": "C:/Users/Heather Bree/chromedriver_win32/chromedriver"}
    browser = Browser("chrome", **executable_path, headless=True)
    listings_details = {}
    for url in rental_urls:
        browser.visit(url)
        html = browser.html
        soup = BeautifulSoup(html, "html.parser")
        details = []
        deleted = []
        keywords = ['dishwasher', 'fireplace', 'garage', 'off-street parking', 'off street parking', 'shed', 'basement', 'storage', 'gas stove', 'gas oven', 'gas range', 'hookups', 'washer/dryer', 'W/D', 'laundry', 'transit', 'bus', 'trimet']
        for tag in soup.descendants:
            if tag.string and 'no longer available' in tag.string:
                delete_listing(url)
                deleted.append(url)
                break
            else:
                if tag.string and '/>' not in tag.string:
                    for word in keywords:
                        # if word in tag.string.lower():
                        if re.search(rf'\b{word}\b', tag.string, flags=re.IGNORECASE):
                            details.append(tag.string)
        deduped_details = list(set(details))
        for i,detail in enumerate(deduped_details):
            styled_detail = detail
            for word in keywords:
                if re.search(rf'\b{word}\b', styled_detail, flags=re.IGNORECASE):
                    styled_detail = styled_detail.replace(word, f"<b>{word}</b>")
                # re.sub(rf'\b{word}\b', f'<b>{word}</b>', detail, flags=re.IGNORECASE)
            deduped_details[i] = styled_detail
        listings_details[url] = deduped_details
    for listing in listings_details.keys():
        if listing in deleted:
            listings_details.pop(listing)
    return listings_details

if __name__ == "__main__":
    app.run()
