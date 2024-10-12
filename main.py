import requests
import json
import sys
from bs4 import BeautifulSoup
import time
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
import os
import platform
import matplotlib.pyplot as plt
from collections import Counter

png_file = 'job_skills_distribution.png'

# Cleanup function to delete the PNG file
def cleanup():
    if os.path.exists(png_file):
        os.remove(png_file)
        print(f"Deleted file: {png_file}")

# nltk.download('stopwords')

def load_config(file_name):
    with open(file_name) as f:
        return json.load(f)

def piechart():
    df = pd.read_csv('jobs_cleaned.csv')
    skills_series = df['job_description']
    skills = skills_series.str.cat(sep=',').split(',')
    skills_count = Counter(skills)    
    totalskills = sum(skills_count.values())
    filtered_skills = {skill:count for skill, count in skills_count.items() if (count/totalskills) >= 0.02}
    
    plt.figure(figsize=(8,8))
    plt.pie(filtered_skills.values(), labels=filtered_skills.keys(), autopct='%1.1f%%', startangle=140)
    plt.title('Job Skills Distribution')
    plt.axis('equal')
    plt.savefig(png_file)
    plt.close()

def get_with_retry(url, config, retries=3, delay=1):
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
        for element in div.find_all(['span', 'a']):
            element.decompose()
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

def remove_duplicates(joblist, config):
    joblist.sort(key=lambda x: (x['title'], x['company']))
    joblist = [next(g) for k, g in groupby(joblist, key=lambda x: (x['title'], x['company']))]
    return joblist

def get_jobcards(config):
    all_jobs = []
    for k in range(0, config['rounds']):
        for query in config['search_queries']:
            keywords = quote(query['keywords'])
            location = quote(query['location'])
            for i in range(0, config['pages_to_scrape']):
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location={location}&f_TPR=&f_WT={query['f_WT']}&geoId=&f_TPR={config['timespan']}&start={25 * i}"
                soup = get_with_retry(url, config)
                jobs = transform(soup)
                all_jobs = all_jobs + jobs
                print("Finished scraping page: ", url)
    print("Total job cards scraped: ", len(all_jobs))
    all_jobs = remove_duplicates(all_jobs, config)
    print("Total job cards after removing duplicates: ", len(all_jobs))
    return all_jobs

def exporttoexcel(all_jobs):
    df = pd.DataFrame(all_jobs)
    df.to_csv('jobs.csv', index=False, header=True)

def extract_skills(text, skillset):
    pattern = '|'.join([re.escape(skill) for skill in skillset])
    found_skills = re.findall(pattern, text, flags=re.IGNORECASE)
    
    # Use a set to avoid duplicates and normalize to lowercase
    unique_skills = set(skill.lower() for skill in found_skills)
    
    # Join the unique skills back to a string, capitalizing only the first letter of each word
    return ', '.join(skill.capitalize() for skill in unique_skills)

def cleanfile():
    stop = stopwords.words('english')
    new_words = ['show','less','Could','not','find','Job','Description', 'go']
    stop = stop + new_words

    skills = [
        'Python', 'Typescript', 'Java', 'JavaScript', 'C#', 'C++', 'PHP', 'Ruby', 'Swift', 'Go', 'Kotlin', 'Perl', 'Bash', 
        'Shell Scripting', 'PowerShell', 'React', 'Angular', 'Vue.js', 'Node.js', 'Express.js', 'Django', 'Flask', 'Laravel', 
        'Spring', '.NET', 'jQuery', 'Bootstrap', 'SASS', 'LESS', 'Android', 'iOS', 'React Native', 'Flutter', 'Kotlin', 
        'Swift', 'Xamarin', 'AWS', 'Amazon Web Services', 'GCP', 'Google Cloud Platform', 'Microsoft Azure', 'Oracle Cloud', 
        'IBM Cloud', 'DigitalOcean', 'Heroku', 'Firebase', 'SQL', 'NoSQL', 'MySQL', 'PostgreSQL', 'MongoDB', 'Cassandra', 
        'Redis', 'Elasticsearch', 'MariaDB', 'DynamoDB', 'BigQuery', 'Snowflake', 'Hadoop', 'Spark', 'ETL', 'Informatica', 
        'DBT', 'Tableau', 'Power BI', 'Talend', 'Airflow', 'Jenkins', 'CircleCI', 'GitLab CI', 'Travis CI', 'Bamboo', 
        'Terraform', 'Ansible', 'Chef', 'Puppet', 'Docker', 'Kubernetes', 'Helm', 'OpenShift', 'TCP/IP', 'DNS', 'SSL/TLS', 
        'VPN', 'SSH', 'IAM', 'OAuth', 'Firewall', 'Penetration Testing', 'Vulnerability Assessment', 'GDPR', 'CEH', 'CISSP', 
        'Agile', 'Scrum', 'Kanban', 'Lean', 'Waterfall', 'SAFe', 'PMP', 'PRINCE2', 'Six Sigma', 'Lean Six Sigma', 'CSM', 
        'Business Analysis', 'Process Improvement', 'Risk Management', 'SWOT Analysis', 'Stakeholder Management', 
        'QuickBooks', 'Xero', 'SAP FICO', 'CPA', 'CIMA', 'Taxation', 'Auditing', 'Financial Reporting', 
        'SEO', 'SEM', 'Google Analytics', 'Salesforce', 'HubSpot', 'CRM', 'Lead Generation', 'Sales Forecasting', 
        'Account Management', 'Shopify', 'Photoshop', 'Illustrator', 'InDesign', 'Sketch', 'Figma', 
        'Final Cut Pro', 'Canva', 'WordPress', 'Medical Coding', 'EHR', 'HIPAA Compliance', 'Patient Care', 'Nursing', 
        'Telemedicine', 'Pharmacy Management', 'Procurement', 'Vendor Management', 'Inventory Management', 'Shipping', 
        'Demand Forecasting', 'Lean Manufacturing', 'ERP', 'Zendesk', 'Freshdesk', 'Salesforce Service Cloud', 
        'Complaint Resolution', 'Technical Support', 'Curriculum Development', 'Lesson Planning', 'Instructional Design', 
        'Learning Management Systems', 'Corporate Training', 'Leadership', 'Teamwork', 'Time Management', 
        'Communication', 'Problem-solving', 'Adaptability', 'Emotional Intelligence', 'Multitasking'
    ]

    # Convert excel_file into a dataframe
    excel_file = 'jobs.csv'
    df = pd.read_csv(excel_file)

    # Remove leading and trailing whitespaces
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x) 

    # -----Cleaning job_description column-----
    # Remove URLs
    url_pattern = re.compile(r'\b(?:https?|ftp|file):\/\/\S+|www\.\S+\b')
    df['job_description'] = df['job_description'].str.replace(url_pattern, '', regex=True) 
    # Remove special characters
    df['job_description'] = df['job_description'].str.replace(r'[^a-zA-Z0-9\s]', '', regex=True) 
    # Remove stopwords
    df['job_description'] = df['job_description'].apply(lambda x: ' '.join([word for word in x.split() if word not in (stop)])) 
    # Extract skills
    df['job_description'] = df['job_description'].apply(lambda x: extract_skills(x, skills))
    # -----End of job_description column cleaning-----

    # Save the cleaned dataframe to a new csv file
    df.to_csv('jobs_cleaned.csv', index=False)
    piechart()

def main(config_file):
    config = load_config(config_file)
    all_jobs = get_jobcards(config)
    job_list = []
    if len(all_jobs) > 0:
        print("Now scraping job descriptions...")
        for job in all_jobs:
            desc_soup = get_with_retry(job['job_url'], config)
            job['job_description'] = transform_job(desc_soup)
            job_list.append(job)
        print("Finished scraping job descriptions")
        df = pd.DataFrame(job_list) 
        df.to_csv('jobs.csv', index=False, header=True)
    exporttoexcel(all_jobs)
    cleanfile()

def wait_for_flask():
    while True:
        try:
            response = requests.get('http://127.0.0.1:5000/')
            if response.status_code == 200:
                print("Flask is running")
                break
        except requests.exceptions.ConnectionError:
            print("Flask is not running yet, waiting...")
            time.sleep(1)

def wait_for_html():
    while True:
        try:
            response = requests.get('http://127.0.0.1:5000/check_form')
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 'success':
                    print("Form input received.")
                    break
                else:
                    print("Waiting for form input...")
            else:
                print("Error checking form input")
        except requests.exceptions.ConnectionError:
            print("Waiting for form input...")
        time.sleep(1)

def reset_form_submission():
    try:
        response = requests.post('http://127.0.0.1:5000/reset_form')
        if response.status_code == 200:
            print("Form submission reset")
        else:
            print("Error resetting form submission")
    except requests.exceptions.ConnectionError:
        print("Error connecting to server to reset form submission")

def openweb():
    filename = 'index.html'
    filepath = os.getcwd()
    file_url = 'file:///' + filepath + '/' + filename
    webbrowser.open_new_tab(file_url)

if __name__ == "__main__":
    cleanup()
    python_command = 'python3' if platform.system() != 'Windows' else 'python'
    subprocess.Popen([python_command, 'flask_server.py'])  # Runs flask code in non-blocking way
    wait_for_flask()
    reset_form_submission()
    openweb()  # Runs html file
    wait_for_html()
    config_file = 'config.json'  # default config file
    main(config_file)