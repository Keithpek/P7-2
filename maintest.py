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
import re
import nltk
from nltk.corpus import stopwords 
import subprocess
import webbrowser

#Comment this line if you have already downloaded the stopwords
#nltk.download('stopwords')

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


def transform(soup):
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
        job_description = ''
        job = {
            'title': title,
            'company': company.text.strip().replace('\n', ' ') if company else '',
            'location': location.text.strip() if location else '',
            'date': date,
            'job_url': job_url,
            'job_description': job_description,
        }
        joblist.append(job)
    return joblist

def transform_job(soup):
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
                jobs = transform(soup)
                all_jobs = all_jobs + jobs
                print("Finished scraping page: ", url)
    print("Total job cards scraped: ", len(all_jobs))
    all_jobs = remove_duplicates(all_jobs, config)
    print("Total job cards after removing duplicates: ", len(all_jobs))
    all_jobs = remove_irrelevant_jobs(all_jobs, config)
    print("Total job cards after removing irrelevant jobs: ", len(all_jobs))
    return all_jobs


def exporttoexcel(all_jobs):
    df = pd.DataFrame(all_jobs)
    df.to_csv('jobs.csv', index=False, header=True)

def extract_skills(text, skillset):
    pattern = '|'.join([re.escape(skill) for skill in skillset])
    found_skills = re.findall(pattern, text, flags=re.IGNORECASE)
    return ', '.join(set([skill.lower() for skill in found_skills]))

def cleanfile():
    stop = stopwords.words('english')
    new_words = ['show','less']
    stop = stop + new_words

    #List of skillsets
    skills = [
        # Programming Languages
        'Python', 'Typescript', 'Nestjs', 'JavaScript', 'Java', 'C#', 'C++', 'Go', 'Ruby', 'Swift', 'PHP', 'Rust', 'R', 'Perl',
        
        # Web Development
        'HTML', 'CSS', 'React', 'Angular', 'Vue.js', 'Node.js', 'Express.js',
        
        # Database Technologies
        'SQL', 'NoSQL', 'MySQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Elasticsearch',
        
        # Cloud Platforms
        'Google Cloud Platform', 'GCP', 'AWS', 'Amazon Web Services', 'Microsoft Azure', 'IBM Cloud', 'Oracle Cloud',
        
        # DevOps and Automation
        'CICD', 'Jenkins', 'Ansible', 'Terraform', 'Chef', 'Puppet', 'GitLab CI/CD',
        
        # Containerization and Orchestration
        'Docker', 'Kubernetes', 'OpenShift', 'Helm',
        
        # Operating Systems
        'Linux', 'Unix', 'Windows Server',
        
        # Networking & Security
        'TCP/IP', 'VPN', 'Firewalls', 'Nginx', 'Apache', 'SSL/TLS', 'Encryption', 'IAM', 'OAuth',
        
        # Data Engineering & Analytics
        'Kafka', 'Hadoop', 'Spark', 'Hive', 'Apache Airflow',
        
        # Machine Learning & Data Science
        'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'Numpy', 'Keras', 'D3.js',
        
        # Other Tools/Frameworks
        'Salesforce', 'SAP', 'Power BI', 'Tableau', 'MATLAB', 'Splunk', 'Elasticsearch'
        ]

    #convert excel_file into a dataframe
    excel_file = 'jobs.csv'
    df = pd.read_csv(excel_file)

    #drop rows with missing values
    df = df.dropna() 

    #Removes leading and trailing whitespaces
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x) 

    #-----Cleaning job_description column-----
    #Removes URLs
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    df['job_description'] = df['job_description'].str.replace(url_pattern, '', regex=True) 
    #Removes special characters
    df['job_description'] = df['job_description'].str.replace(r'[^a-zA-Z0-9\s]', '', regex=True) 
    #Removes stopwords
    df['job_description'] = df['job_description'].apply(lambda x: ' '.join([word for word in x.split() if word.lower() not in (stop)])) 
    #Extracts skills
    df['job_description'] = df['job_description'].apply(lambda x: extract_skills(x, skills))
    #-----End of job_description column cleaning-----

    #Save the cleaned dataframe to a new csv file
    df.to_csv('jobs_cleaned.csv', index=False)

def main(config_file):
    config = load_config(config_file)
    all_jobs = get_jobcards(config)
    job_list = []
    if len(all_jobs) > 0:
        for job in all_jobs:
            desc_soup = get_with_retry(job['job_url'], config)
            job['job_description'] = transform_job(desc_soup)
            job_list.append(job)
            #jobs_to_add = remove_irrelevant_jobs(job_list, config)
            df = pd.DataFrame(job_list)
            df.to_csv('jobs.csv', index=False, header=True)
    exporttoexcel(all_jobs)
    cleanfile()


if __name__ == "__main__":
    subprocess.Popen(['python', 'flask_test.py']) #Runs flask code in non-blocking way
    webbrowser.open('ui_test.html') #Runs html file
    config_file = 'config.json'  # default config file
    if len(sys.argv) == 2:
        config_file = sys.argv[1]

    main(config_file)