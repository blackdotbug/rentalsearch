from splinter import Browser
from bs4 import BeautifulSoup
from time import sleep
import json
import requests
from config import apikey

def geocode(address):
    address = address.replace(" ", "+")
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address},+Portland,+OR&key={apikey}"
    response = requests.get(url)
    if response.json()['status'] == "REQUEST_DENIED":
        coords = ""
    else:
        coords = response.json()['results'][0]['geometry']['location']
    return coords

def scrape_site(site, browser):
    scrape_stats = {}
    rentals = {}
    try:
        base_url = site['base url']
        if "interact" in site.keys():
            search_url = site['interact']['search url']
            browser.visit(base_url + search_url)
            sleep(2)
            browser.is_element_present_by_css(site['interact']['open'], wait_time=10)
            sleep(2)
            browser.find_by_css(site['interact']['open']).click()
            sleep(2)
            if 'typecheck' in site['interact'].keys():
                browser.find_by_css(site['interact']['typecheck'][0]).click()
                sleep(0.25)
                browser.check(site['interact']['typecheck'][1])
            if 'citycheck' in site['interact'].keys():
                browser.find_by_css(site['interact']['citycheck'][0]).click()
                sleep(0.25)
                browser.check(site['interact']['citycheck'][1])
            if 'bedscheck' in site['interact'].keys():
                browser.find_by_css(site['interact']['bedscheck'][0]).click()
                sleep(0.25)
                browser.check(site['interact']['bedscheck'][1])
                browser.check(site['interact']['bedscheck'][2])
            if 'petscheck' in site['interact'].keys():
                browser.find_by_css(site['interact']['petscheck'][0]).click()
                sleep(0.25)
                browser.check(site['interact']['petscheck'][1])
            if 'catselect' in site['interact'].keys():
                sleep(0.25)
                browser.select(site['interact']['catselect'][0],site['interact']['catselect'][1])
            if 'bedselect' in site['interact'].keys():
                sleep(0.25)
                browser.select(site['interact']['bedselect'][0],site['interact']['bedselect'][1])
            if 'cityselect' in site['interact'].keys():
                sleep(0.25)
                browser.select(site['interact']['cityselect'][0],site['interact']['cityselect'][1])
            if site['interact']['submit'][0] == "link by id":
                browser.click_link_by_id(site['interact']['submit'][1])
            elif site['interact']['submit'][0] == "find by css":
                browser.find_by_css(site['interact']['submit'][1]).click()
            if site['base url'].find("appfolio"):
                if browser.is_text_present("All available listings", wait_time=2):
                    scrape_stats[site['home url']] = "filtering failed, site skipped"

        else:
            search_url = site['search url']
            browser.visit(base_url + search_url)

        if browser.is_element_present_by_css('div#result_container.is-loading', wait_time=2):
            sleep(1)

        html = browser.html
        soup = BeautifulSoup(html, "html.parser")
        listings = soup.select(site['listing container'])
        for listing in listings:
            skip = False
            if "cat text" in site.keys():
                skip = True
                find_cats = listing.select_one(site["cat text"][0])
                if find_cats:
                    for li in find_cats.descendants:
                        if li.string and site["cat text"][1] in li.string:
                            skip = False
                            break
            if skip == True:
                break

            address = ""
            if "address" in site.keys():
                find_address = listing.find(site['address'][0], class_=site['address'][1])
                if find_address:
                    address = find_address.get_text().replace('\t', '').replace('\n','')
                    if any(x in address.lower() for x in ['gresham','wilsonville','sherwood', 'beaverton', 'tigard', 'oswego', 'hillsboro']):
                        break
                    if address.find(", Portland, OR") > 0:
                        address = address[0:address.rfind(", Portland, OR")]
                    elif address.find("Portland, OR") > 0:
                        address = address[0:address.rfind("Portland, OR")]
                    elif address.find(", OR") > 0:
                        address = address[0:address.rfind(", OR")]
            rent = ""
            if "rent" in site.keys():
                find_rent = ""
                if type(site['rent']) == str:
                    find_rent = listing.select_one(site['rent'])
                else:
                    find_rent = listing.find(site['rent'][0], class_=site['rent'][1])
                if find_rent:
                    rent = find_rent.get_text().replace('.00','')
                    rent = ''.join(i for i in rent if i.isdigit())
            beds = ""
            if "beds" in site.keys():
                find_beds = ""
                if type(site['beds']) == str:
                    if len(site['beds']) > 2:
                        find_beds = listing.select_one(site['beds'])
                    else:
                        find_beds = site['beds']
                else:
                    find_beds = listing.find(site['beds'][0], class_=site['beds'][1])
                if find_beds:
                    if type(find_beds) == str:
                        beds = find_beds
                    else:
                        beds = find_beds.get_text()

            sqft = ""
            if "sqft" in site.keys():
                find_sqft = ""
                if type(site['sqft']) == str:
                    find_sqft = listing.select_one(site['sqft'])
                else:
                    find_sqft = listing.find(site['sqft'][0], class_=site['sqft'][1])
                if find_sqft:
                    sqft = ''.join(i for i in find_sqft.get_text() if i.isdigit())
            link = ""
            if "link" in site.keys():
                if type(site['link']) == str:
                    if site['link'] == "self":
                        link = listing.get("href")
                    else:
                        link = listing.select_one(site['link']).get("href")
                else:
                    link = listing.find(site['link'][0], class_=site['link'][1]).get("href")
            img = ""
            if "img" in site.keys():
                find_img = listing.select_one(site['img'][1])
                if site['img'][0] == "style":
                    if find_img:
                        img = find_img['style']
                        img = img[img.find("(")+len("("):img.rfind(")")]
                        if img[0] == "'":
                            img = img[1:len(img)-1]
                        elif img[0] == "/":
                            img = "https:"+img
                elif site['img'][0] == "img src full link":
                    if find_img:
                        img = find_img['src']

            lat = 45.523064
            lng = -122.676483
            coords = geocode(address)
            if coords:
                lat = coords['lat']
                lng = coords['lng']

            rental = {
                "address": address,
                "rent": rent,
                "beds": beds,
                "sqft": sqft,
                "link": base_url + link,
                "img": img,
                "lat": lat,
                "lng": lng
            }

            rentals[rental['address']] = rental
        if 'home url' in site.keys() and len(rentals) > 0:
            scrape_stats[site['home url']] = len(rentals)
        elif 'home url' in site.keys():
            scrape_stats[site['home url']] = "no properties found"
        else:
            if len(rentals) > 0:
                scrape_stats[site['base url']] = len(rentals)
            else:
                scrape_stats[site['base url']] = "no properties found"

        return rentals, scrape_stats

    except Exception as e:
        print(e)
        if 'home url' in site.keys():
            if len(scrape_stats) == 0:
                scrape_stats[site['home url']] = "something went wrong, site skipped"
        else:
            scrape_stats[site['base url']] = "something went wrong, site skipped"
        return rentals, scrape_stats

def scrape_all(home_url = 'all'):
    browser = Browser("chrome", headless=False)

    rentals = {}

    with open('searches.json') as json_file:
            data = json.load(json_file)
            scrape_stats = {}
            for site in data:
                if home_url == 'all':
                    site_rentals, site_scrape_stats = scrape_site(site, browser)
                    scrape_stats.update(site_scrape_stats)
                    rentals.update(site_rentals)
                else:
                    if ('home url' in site.keys() and site['home url'] == home_url) or site['base url'] == home_url:
                        browser = Browser("chrome", headless=True)
                        site_rentals, site_scrape_stats = scrape_site(site, browser)
                        scrape_stats.update(site_scrape_stats)
                        rentals.update(site_rentals)

    browser.quit
    return rentals, scrape_stats

if __name__ == "__main__":

    # If running as script, print scraped data
    print(scrape_all())
