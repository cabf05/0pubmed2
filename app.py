import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import requests
from collections import Counter
import re

st.set_page_config(page_title="PubMed Relevance Finder", layout="wide")
st.title("🔎 PubMed Relevance Finder")

# --- User Inputs ---
with st.expander("🔧 Settings", expanded=True):
    query = st.text_input("Enter PubMed search term:", value="GLP-1 diabetes cardiovascular outcomes")
    top_journals_input = st.text_area(
        "Top Journals (comma-separated)",
        value="New England Journal of Medicine, JAMA, The Lancet, Nature, Cell, Science, BMJ",
        height=100
    )
    top_institutions_input = st.text_area(
        "Top Institutions (comma-separated)",
        value="Harvard, Oxford, Cambridge, Stanford, Johns Hopkins, MIT, Mayo Clinic, UCSF, Yale, Karolinska",
        height=100
    )
    max_results = st.slider("Number of articles", 10, 200, 50)

top_journals = [j.strip() for j in top_journals_input.split(",") if j.strip()]
top_institutions = [i.strip() for i in top_institutions_input.split(",") if i.strip()]

# --- Helper function to fetch PubMed data ---
@st.cache_data(show_spinner=True)
def fetch_pubmed(query, max_results):
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax={max_results}&retmode=xml&term={query}"
    res = requests.get(url)
    root = ET.fromstring(res.content)
    ids = [id_elem.text for id_elem in root.findall(".//Id")]

    # Fetch summaries
    id_string = ",".join(ids)
    fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={id_string}&retmode=xml"
    fetch_res = requests.get(fetch_url)
    return ET.fromstring(fetch_res.content)

# --- Parse XML and build DataFrame ---
def parse_articles(xml_root):
    articles = []
    for article in xml_root.findall(".//PubmedArticle"):
        title = article.findtext(".//ArticleTitle", default="N/A")
        journal = article.findtext(".//Journal/Title", default="N/A")
        pub_date_elem = article.find(".//PubDate")
        pub_year = pub_date_elem.findtext("Year") if pub_date_elem is not None else "N/A"

        affiliations = []
        for aff_elem in article.findall(".//AffiliationInfo/Affiliation"):
            affiliations.append(aff_elem.text)

        articles.append({
            "Title": title,
            "Journal": journal,
            "Year": pub_year,
            "Affiliations": "; ".join(affiliations)
        })
    return pd.DataFrame(articles)

# --- Fetch & Parse ---
with st.spinner("Searching PubMed..."):
    xml_root = fetch_pubmed(query, max_results)
    df = parse_articles(xml_root)

# --- Relevance Scoring ---
def compute_score(row):
    score = 0
    # Journal match
    if any(j.lower() in row["Journal"].lower() for j in top_journals):
        score += 1
    # Institution match
    for aff in row["Affiliations"].split(";"):
        aff_lower = aff.lower()
        for inst in top_institutions:
            pattern = r"\b" + re.escape(inst.lower()) + r"\b"
            if re.search(pattern, aff_lower):
                score += 1
                break  # avoid double counting for same row
    return score

df["Score"] = df.apply(compute_score, axis=1)
df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)

# --- Display Table ---
st.subheader("📄 Article Table Sorted by Relevance Score")
st.dataframe(df[["Score", "Year", "Journal", "Title"]], use_container_width=True)

# --- Summary Analytics ---
st.subheader("📊 Summary Stats")

# 1. Journals
journal_counter = Counter(df["Journal"])
st.markdown("**Top Journals in Results:**")
st.table(pd.DataFrame(journal_counter.most_common(10), columns=["Journal", "Count"]))

# 2. Institutions in Affiliations
st.subheader("🏅 Renowned Institutions Mencionadas")
inst_counter = Counter()

for aff in df["Affiliations"]:
    aff_split = [a.strip() for a in re.split(r';', aff) if a.strip()]
    for inst in top_institutions:
        pattern = r"\b" + re.escape(inst.lower()) + r"\b"
        for sub_aff in aff_split:
            if re.search(pattern, sub_aff.lower()):
                inst_counter[inst] += 1

st.table(pd.DataFrame(inst_counter.most_common(), columns=["Institution", "Count"]))
