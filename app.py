import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from urllib.parse import quote
from collections import Counter
from itertools import chain
import plotly.express as px

st.set_page_config(page_title="PubMed Relevance Analyzer", layout="wide")

st.title("🔎 PubMed Article Relevance Analyzer")

# --- Input fields ---
query = st.text_area("📝 Enter your PubMed query", 
    value='(("Lancet Diabetes Endocrinol"[Journal] OR "N Engl J Med"[Journal] OR "Lancet"[Journal] OR "JAMA"[Journal] OR "BMJ"[Journal]) AND ("Endocrinology"[All Fields] OR "Diabetes"[All Fields]) AND (("case reports"[Publication Type] OR "clinical trial"[Publication Type] OR "controlled clinical trial"[Publication Type] OR "dataset"[Publication Type] OR "guideline"[Publication Type] OR "meta analysis"[Publication Type] OR "multicenter study"[Publication Type] OR "practice guideline"[Publication Type] OR "randomized controlled trial"[Publication Type] OR "review"[Publication Type] OR "systematic review"[Filter]) AND 2024/10/01:2025/06/28[Date - Publication]))')

impact_journals = st.text_area("🏅 List 7 high-impact journals (one per line)", 
    value="N Engl J Med\nLancet\nJAMA\nBMJ\nLancet Diabetes Endocrinol\nJAMA Intern Med\nAnn Intern Med"
).splitlines()

institutions = st.text_area("🏥 List 10 renowned institutions (one per line)", 
    value="Harvard University\nStanford University\nJohns Hopkins University\nUniversity of Oxford\nUCSF\nMayo Clinic\nYale University\nUniversity of Toronto\nKarolinska Institute\nImperial College London"
).splitlines()

hot_keywords = st.text_area("🔥 List hot keywords to score (one per line)", 
    value="GLP-1\nsemaglutide\ntirzepatide\nobesity\nweight loss\nremission\nglucose control\nHbA1c\ncardiovascular\nSGLT2"
).lower().splitlines()

max_results = st.slider("🔢 Number of articles to retrieve", min_value=10, max_value=250, value=100, step=10)

@st.cache_data(show_spinner=False)
def fetch_pmids(query, retmax):
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax={retmax}&term={quote(query)}"
    response = requests.get(url)
    root = ET.fromstring(response.content)
    return [id_tag.text for id_tag in root.findall(".//Id")]

@st.cache_data(show_spinner=False)
def fetch_article(pmid):
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
    response = requests.get(url)
    root = ET.fromstring(response.content)
    article = root.find(".//PubmedArticle")

    def get_text(path):
        el = article.find(path)
        return el.text if el is not None else ""

    title = get_text(".//ArticleTitle")
    journal = get_text(".//Journal/Title")
    date = get_text(".//PubDate/Year") or get_text(".//PubDate/MedlineDate")
    abstract = " ".join([abst.text or "" for abst in article.findall(".//AbstractText")])

    authors = []
    for a in article.findall(".//Author"):
        last = a.findtext("LastName")
        fore = a.findtext("ForeName")
        if last and fore:
            authors.append(f"{fore} {last}")
    authors_str = ", ".join(authors)

    affiliations = "; ".join([aff.text for aff in article.findall(".//AffiliationInfo/Affiliation") if aff is not None])

    pub_types = "; ".join([pt.text for pt in article.findall(".//PublicationType") if pt is not None])

    citation = f"{authors_str} ({date}). {title}. {journal}."

    return {
        "PMID": pmid,
        "Title": title,
        "Authors": authors_str,
        "Journal": journal,
        "Date": date,
        "Abstract": abstract,
        "Affiliations": affiliations,
        "Publication Types": pub_types,
        "Citation": citation
    }

if st.button("🔍 Run PubMed Search"):
    with st.spinner("Searching PubMed..."):
        pmids = fetch_pmids(query, max_results)
        data = []
        for pmid in pmids:
            try:
                article = fetch_article(pmid)
                score = 0
                if any(j.lower() in article["Journal"].lower() for j in impact_journals):
                    score += 1
                if any(inst.lower() in article["Affiliations"].lower() for inst in institutions):
                    score += 1
                if any(kw in article["Title"].lower() for kw in hot_keywords):
                    score += 1
                article["Relevance Score (0-3)"] = score
                data.append(article)
            except Exception as e:
                st.warning(f"Error processing PMID {pmid}: {e}")

        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values(by="Relevance Score (0-3)", ascending=False)
            st.success(f"✅ {len(df)} articles retrieved and scored.")
            st.dataframe(df)

            st.download_button("⬇️ Download CSV", data=df.to_csv(index=False), file_name="pubmed_articles.csv", mime="text/csv")

            # --- Summary Analysis ---
            st.header("📊 Summary Analysis")

            # Articles per Journal
            st.subheader("🔬 Articles per Journal")
            journal_counts = df["Journal"].value_counts().reset_index()
            journal_counts.columns = ["Journal", "Count"]
            st.plotly_chart(px.bar(journal_counts, x="Journal", y="Count", title="Articles per Journal"))
            st.dataframe(journal_counts)

            # Articles per Institution
            st.subheader("🏥 Articles mentioning Renowned Institutions")
            inst_counter = Counter()
            for aff in df["Affiliations"]:
                for inst in institutions:
                    if inst.lower() in aff.lower():
                        inst_counter[inst] += 1
            inst_df = pd.DataFrame(inst_counter.items(), columns=["Institution", "Count"]).sort_values("Count", ascending=False)
            if not inst_df.empty:
                st.plotly_chart(px.bar(inst_df, x="Institution", y="Count", title="Articles per Institution"))
                st.dataframe(inst_df)
            else:
                st.info("No matches found for institutions in affiliations.")

            # Articles per Publication Type
            st.subheader("📄 Articles per Publication Type")
            pubtype_list = list(chain.from_iterable([pt.split("; ") for pt in df["Publication Types"]]))
            pubtype_counts = pd.Series(pubtype_list).value_counts().reset_index()
            pubtype_counts.columns = ["Publication Type", "Count"]
            st.plotly_chart(px.bar(pubtype_counts, x="Publication Type", y="Count", title="Publication Types"))
            st.dataframe(pubtype_counts)

            # Hot Keywords in Title
            st.subheader("🔥 Hot Keywords in Title")
            hot_counter = Counter()
            for title in df["Title"]:
                for kw in hot_keywords:
                    if kw in title.lower():
                        hot_counter[kw] += 1
            hot_df = pd.DataFrame(hot_counter.items(), columns=["Hot Keyword", "Count"]).sort_values("Count", ascending=False)
            if not hot_df.empty:
                st.plotly_chart(px.bar(hot_df, x="Hot Keyword", y="Count", title="Hot Keywords in Titles"))
                st.dataframe(hot_df)
            else:
                st.info("No hot keywords found in article titles.")
