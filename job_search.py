import os
import smtplib
import anthropic
import pandas as pd
from serpapi import GoogleSearch
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ============================================================
# EDIT THESE
# ============================================================

MY_PROFILE = """I have a bachelors degree in statistics and a masters in applied statistics. No experience
Skills: Statistical Analysis, Machine Learning, Data Preprocessing, Data Visualization
Software: Expert in R. Experience with Python, Excel, Word, PowerPoint, SAS, SQL.
Previous Experience: Tutor, Teaching Assistant
Want: remote, hybrid, in-person, $50,000+. No New York City
"""

MY_EMAIL = "ethan.straub@icloud.com"  # your email address

QUERIES = [
    "Entry Level Statistician",
    "Biostatistician",
    "Research Assistant",
    "Research Associate",
    "R programmer"
]

# ============================================================
# DON'T EDIT ANYTHING BELOW THIS LINE
# ============================================================

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


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
        print(f"\nSearching: {query}")
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
    df = pd.DataFrame(results)
    df = df.sort_values("score", ascending=False)
    df.to_csv("jobs.csv", index=False)

    top_jobs = df[df["score"].astype(str) >= "7"]
    send_email("jobs.csv", top_jobs)
