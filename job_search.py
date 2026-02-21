import os
import smtplib
import anthropic
import pandas as pd
from serpapi import GoogleSearch
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from exa_py import Exa

# ============================================================
# EDIT THESE
# ============================================================

MY_PROFILE = """Bachelors degree in statistics. Masters in applied statistics. No experience
Skills: Statistical/Data Analysis, Machine Learning, data management and querying (dplyr), 
visualization (ggplot2), modeling(regression, A/B testing, GLMs, mixed models), 
predictive analysis (Random forest, XGBoost, penalized regression...), 
bayesian methods (base R, Stan, rstanarm, rjags), Python coding for predictive analysis (ski-kit learn, NumPy, pandas, Keras, tensorflow)
I passed the society of actuaries SOA Exam P. Clinical Project experience: Traumatic Brain Injury
Software: Expert in R. Experience with Python, Excel, Word, PowerPoint, Power BI, SAS, SQL.
Previous Experience: Tutor, Teaching Assistant, Dining hall supervisor, home depot lumber associate, arborist, golf course maintenance
Want: remote, hybrid, in-person, $50,000+. Anywhere in the United States except New York City
"""

MY_EMAIL = "ethan.straub@icloud.com"  # your email address

QUERIES = [
    "Biostatistician OR Statistical Analyst OR Research Associate OR Research Assistant OR Actuarial Analyst",
]

# ============================================================
# DON'T EDIT ANYTHING BELOW THIS LINE
# ============================================================

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
print(f"SERPAPI_KEY length: {len(SERPAPI_KEY)}")  # ADD THIS - shows length without exposing the key

def fetch_jobs(query, location="United States", num_results=10):
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    return results.get("jobs_results", [])[:num_results]

def fetch_jobs_exa(query, num_results=10):
    exa = Exa(api_key=os.environ["EXA_API_KEY"])
    results = exa.search_and_contents(
        query,
        num_results=num_results,
        include_domains=[
            "jobs.apha.org",        # public health jobs
            "jobs.amstat.org",      # statistics jobs
            "higheredjobs.com",     # university jobs
            "usajobs.gov",          # government jobs
            "biospace.com",         # biotech/pharma jobs
        ],
        text={"max_characters": 1000}
    )
    
    jobs = []
    for result in results.results:
        jobs.append({
            "title": result.title,
            "company_name": "See listing",
            "location": "See listing",
            "description": result.text,
            "related_links": [{"link": result.url}]
        })
    return jobs

def score_job(job):
    description = job.get("description", "No description available")[:1500]

    prompt = f"""
Candidate profile:
{MY_PROFILE}

Job posting:
Title: {job.get('title')}
Company: {job.get('company_name')}
Location: {job.get('location')}
Description: {description}

Rate this job's fit for the candidate on a scale of 1-10.
Reply in this exact format:
SCORE: <number>
REASON: <one sentence>
APPLY: <yes/no>
"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


def parse_score(score_text):
    lines = score_text.strip().split("\n")
    result = {}
    for line in lines:
        if line.startswith("SCORE:"):
            result["score"] = line.replace("SCORE:", "").strip()
        elif line.startswith("REASON:"):
            result["reason"] = line.replace("REASON:", "").strip()
        elif line.startswith("APPLY:"):
            result["apply"] = line.replace("APPLY:", "").strip()
    return result


def run_agent(queries):
    all_results = []

    for query in queries:
        # Google Jobs search
        print(f"\nSearching Google Jobs: {query}")
        jobs = fetch_jobs(query)
        print(f"Found {len(jobs)} jobs")

        for job in jobs:
            print(f"  Scoring: {job.get('title')} @ {job.get('company_name')}...")
            score_text = score_job(job)
            parsed = parse_score(score_text)
            all_results.append({
                "title": job.get("title"),
                "company": job.get("company_name"),
                "location": job.get("location"),
                "score": parsed.get("score", "?"),
                "reason": parsed.get("reason", ""),
                "apply": parsed.get("apply", "?"),
                "link": job.get("related_links", [{}])[0].get("link", ""),
            })

        # Exa search
        print(f"\nSearching Exa: {query}")
        exa_jobs = fetch_jobs_exa(query)
        print(f"Found {len(exa_jobs)} jobs")

        for job in exa_jobs:
            print(f"  Scoring: {job.get('title')}...")
            score_text = score_job(job)
            parsed = parse_score(score_text)
            all_results.append({
                "title": job.get("title"),
                "company": job.get("company_name"),
                "location": job.get("location"),
                "score": parsed.get("score", "?"),
                "reason": parsed.get("reason", ""),
                "apply": parsed.get("apply", "?"),
                "link": job.get("related_links", [{}])[0].get("link", ""),
            })

    return all_results


def send_email(csv_path, top_jobs):
    msg = MIMEMultipart()
    msg["From"] = MY_EMAIL
    msg["To"] = MY_EMAIL
    msg["Subject"] = f"🎯 Job Agent: {len(top_jobs)} new matches found today"

    if len(top_jobs) == 0:
        body = "No strong matches found today (score 7+). Full results attached."
    else:
        body = "Here are your top job matches today:\n\n"
        for _, row in top_jobs.iterrows():
            body += f"{row['title']} @ {row['company']}\n"
            body += f"Score: {row['score']} | {row['reason']}\n"
            body += f"Link: {row['link']}\n"
            body += "-" * 40 + "\n"

    msg.attach(MIMEText(body, "plain"))

    with open(csv_path, "rb") as f:
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment; filename=jobs.csv")
        msg.attach(attachment)

    with smtplib.SMTP("smtp.mail.me.com", 587) as server:
        server.starttls()
        server.login(MY_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(MY_EMAIL, MY_EMAIL, msg.as_string())

    print("Email sent!")


if __name__ == "__main__":
    results = run_agent(QUERIES)
    
    if not results:
        print("No jobs found. Try different search queries.")
    else:
        df = pd.DataFrame(results)
        df = df.sort_values("score", ascending=False)
        df.to_csv("jobs.csv", index=False)

        top_jobs = df[df["score"].astype(str) >= "7"]
        send_email("jobs.csv", top_jobs)
