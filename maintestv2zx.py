import requests
import json
import sys
from bs4 import BeautifulSoup
import time as tm
from itertools import groupby
import pandas as pd
from urllib.parse import quote
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException


def load_config(file_name):
    # Load the config file
    with open(file_name) as f:
        return json.load(f)


def get_with_retry(url, config, retries=3, delay=1):
    # Get the URL with retries and delay
    for i in range(retries):
        try:
            if len(config['proxies']) > 0:
                r = requests.get(url, headers=config['headers'], proxies=config['proxies'], timeout=5)
            else:
                r = requests.get(url, headers=config['headers'], timeout=5)
            return BeautifulSoup(r.content, 'html.parser')
        except requests.exceptions.Timeout:
            print(f"Timeout occurred for URL: {url}, retrying in {delay}s...")
            tm.sleep(delay)
        except Exception as e:
            print(f"An error occurred while retrieving the URL: {url}, error: {e}")
    return None


def transform(soup, config):
    # Parsing the job card info (title, company, location, date, job_url) from the beautiful soup object
    joblist = []
    try:
        divs = soup.find_all('div', class_='base-search-card__info')
    except:
        print("Empty page, no jobs found")
        return joblist
    
    for item in divs:
        title = item.find('h3').text.strip()
        company = item.find('a', class_='hidden-nested-link')
        location = item.find('span', class_='job-search-card__location')
        parent_div = item.parent
        entity_urn = parent_div['data-entity-urn']
        job_posting_id = entity_urn.split(':')[-1]
        job_url = 'https://www.linkedin.com/jobs/view/' + job_posting_id + '/'

        date_tag_new = item.find('time', class_='job-search-card__listdate--new')
        date_tag = item.find('time', class_='job-search-card__listdate')
        date = date_tag['datetime'] if date_tag else date_tag_new['datetime'] if date_tag_new else ''
        job_description = get_job_description(job_url, config)
        job = {
            'title': title,
            'company': company.text.strip().replace('\n', ' ') if company else '',
            'location': location.text.strip() if location else '',
            'date': date,
            'job_url': job_url,
            'job_description': job_description,
            'applied': 0,
            'hidden': 0,
            'interview': 0,
            'rejected': 0
        }
        joblist.append(job)
    return joblist

def get_job_description(job_url, config):
    soup = get_with_retry(job_url, config)
    if not soup:
        return "Could not retrieve description"

    div = soup.find('div', class_='description__text description__text--rich')
    if div:
        for element in div.find_all(['span', 'a']):
            element.decompose()

        text = div.get_text(separator='\n').strip()
        text = text.replace('\n\n', '')
        text = text.replace('Show less', '').replace('Show more', '')
        return text
    else:
        return "Could not find Job Description"

    # def transform_job(soup):
    div = soup.find('div', class_='description__text description__text--rich')
    if div:
        # Remove unwanted elements
        for element in div.find_all(['span', 'a']):
            element.decompose()

        # Replace bullet points
        for ul in div.find_all('ul'):
            for li in ul.find_all('li'):
                li.insert(0, '-')

        text = div.get_text(separator='\n').strip()
        text = text.replace('\n\n', '')
        text = text.replace('::marker', '-')
        text = text.replace('-\n', '- ')
        text = text.replace('Show less', '').replace('Show more', '')
        return text
    else:
        return "Could not find Job Description"


def safe_detect(text):
    try:
        return detect(text)
    except LangDetectException:
        return 'en'


def remove_irrelevant_jobs(joblist, config):
    # Filter out jobs based on description, title, and language. Set up in config.json.
    new_joblist = [job for job in joblist if
                   not any(word.lower() in job['job_description'].lower() for word in config['desc_words'])]
    new_joblist = [job for job in new_joblist if
                   not any(word.lower() in job['title'].lower() for word in config['title_exclude'])] if len(
        config['title_exclude']) > 0 else new_joblist
    new_joblist = [job for job in new_joblist if
                   any(word.lower() in job['title'].lower() for word in config['title_include'])] if len(
        config['title_include']) > 0 else new_joblist
    new_joblist = [job for job in new_joblist if safe_detect(job['job_description']) in config['languages']] if len(
        config['languages']) > 0 else new_joblist
    new_joblist = [job for job in new_joblist if
                   not any(word.lower() in job['company'].lower() for word in config['company_exclude'])] if len(
        config['company_exclude']) > 0 else new_joblist

    return new_joblist


def remove_duplicates(joblist, config):
    # Remove duplicate jobs in the joblist. Duplicate is defined as having the same title and company.
    joblist.sort(key=lambda x: (x['title'], x['company']))
    joblist = [next(g) for k, g in groupby(joblist, key=lambda x: (x['title'], x['company']))]
    return joblist


def get_jobcards(config):
    # Function to get the job cards from the search results page
    all_jobs = []
    for k in range(0, config['rounds']):
        for query in config['search_queries']:
            keywords = quote(query['keywords'])  # URL encode the keywords
            location = quote(query['location'])  # URL encode the location
            for i in range(0, config['pages_to_scrape']):
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location={location}&f_TPR=&f_WT={query['f_WT']}&geoId=&f_TPR={config['timespan']}&start={25 * i}"
                soup = get_with_retry(url, config)
                jobs = transform(soup, config)
                all_jobs.extend(jobs)
                print("Finished scraping page: ", url)
    print("Total job cards scraped: ", len(all_jobs))
    all_jobs = remove_duplicates(all_jobs, config)
    print("Total job cards after removing duplicates: ", len(all_jobs))
    all_jobs = remove_irrelevant_jobs(all_jobs, config)
    print("Total job cards after removing irrelevant jobs: ", len(all_jobs))
    return all_jobs


def exporttoexcel(all_jobs):
    if not all_jobs:  # Check if there are no jobs to export
        print("No jobs to export.")
        return
    df = pd.DataFrame(all_jobs)
    print("Columns in DataFrame:", df.columns.tolist())  # Debugging line
    
    # Specify the columns you want to keep
    relevant_columns = ['title', 'company', 'location', 'date', 'job_url', 'job_description']
    
    # Check if all relevant columns exist in the DataFrame
    if all(col in df.columns for col in relevant_columns):
        df[relevant_columns].to_csv('jobs.csv', index=False)  # Exports using DataFrame column names as headers
    else:
        print("Mismatch between relevant columns and actual DataFrame columns.")


def main(config_file):
    config = load_config(config_file)
    all_jobs = get_jobcards(config)
    exporttoexcel(all_jobs)


if __name__ == "__main__":
    config_file = 'config.json'  # default config file
    if len(sys.argv) == 2:
        config_file = sys.argv[1]

    main(config_file)