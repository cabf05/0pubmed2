import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
from collections import Counter
from itertools import chain

st.set_page_config(page_title="PubMed Relevance Ranker", layout="wide")
st.title("🔍 PubMed Relevance Ranker")
st.markdown("Fetch and rank recent PubMed articles based on relevance potential using custom criteria.")

# -------------------- Inputs --------------------
st.header("Step 1: Customize the Search")

default_query = '("Endocrinology" OR "Diabetes") AND 2024/10/01:2025/06/28[Date - Publication]'
query = st.text_area("PubMed Search Query", value=default_query, height=100)

default_journals = "\n".join([
    "N Engl J Med", "JAMA", "BMJ", "Lancet", "Nature", "Science", "Cell"
])
journal_input = st.text_area("High-Impact Journals (one per line)", value=default_journals, height=150)
journals = [j.strip().lower() for j in journal_input.strip().split("\n") if j.strip()]

default_institutions = "\n".join([
    "Harvard", "Oxford", "Mayo Clinic", "NIH", "Stanford",
    "UCSF", "Yale", "Cambridge", "Karolinska", "Johns Hopkins"
])
inst_input = st.text_area("Renowned Institutions (one per line)", value=default_institutions, height=150)
institutions = [i.strip().lower() for i in inst_input.strip().split("\n") if i.strip()]

default_keywords = "\n".join([
    "glp-1", "semaglutide", "tirzepatide", "ai", "machine learning", "telemedicine"
])
hot_input = st.text_area("Hot Keywords (one per line)", value=default_keywords, height=100)
hot_keywords = [k.strip().lower() for k in hot_input.strip().split("\n") if k.strip()]

max_results = st.number_input("Max number of articles to fetch", min_value=10, max_value=1000, value=250, step=10)

# -------------------- Utility Functions --------------------
def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip().lower()

def match_renowned_institution(text, institution_list):
    text = normalize_text(text)
    for inst in institution_list:
        if re.search(rf"\b{re.escape(inst.lower())}\b", text):
            return True
    return False

def split_affiliations(raw_aff):
    return [normalize_text(part) for part in re.split(r"[;,]", raw_aff) if part.strip()]

# -------------------- Search and Processing --------------------
if st.button("🔎 Run PubMed Search"):
    with st.spinner("Fetching articles..."):

        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "retmax": str(max_results),
            "retmode": "json",
            "term": query
        }
        r = requests.get(search_url, params=search_params)
        id_list = r.json()["esearchresult"].get("idlist", [])

        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml"
        }
        response = requests.get(efetch_url, params=params, timeout=20)

        parsed_ok = 0
        parsed_fail = 0
        records = []

        def score_article(article, aff_parts, title_text):
            score = 0
            reasons = []

            journal = article.findtext(".//Journal/Title", "").lower()
            if any(j in journal for j in journals):
                score += 2
                reasons.append("High-impact journal (+2)")

            pub_types = [pt.text.lower() for pt in article.findall(".//PublicationType")]
            valued_types = ["randomized controlled trial", "systematic review", "meta-analysis", "guideline", "practice guideline"]
            if any(pt in valued_types for pt in pub_types):
                score += 2
                reasons.append("Valued publication type (+2)")

            authors = article.findall(".//Author")
            if len(authors) >= 5:
                score += 1
                reasons.append("Multiple authors (+1)")

            if any(match_renowned_institution(aff, institutions) for aff in aff_parts):
                score += 1
                reasons.append("Prestigious institution (+1)")

            if any(kw in title_text for kw in hot_keywords):
                score += 2
                reasons.append("Hot keyword in title (+2)")

            if article.find(".//GrantList") is not None:
                score += 2
                reasons.append("Has research funding (+2)")

            return score, "; ".join(reasons)

        def build_citation(article):
            authors = article.findall(".//Author")
            if authors:
                first_author = authors[0]
                last = first_author.findtext("LastName", "")
                initials = first_author.findtext("Initials", "")
                author_text = f"{last} {initials}" if last else "Unknown Author"
            else:
                author_text = "Unknown Author"
            year = article.findtext(".//PubDate/Year") or "n.d."
            title = article.findtext(".//ArticleTitle", "").strip()
            journal = article.findtext(".//Journal/Title", "")
            return f"{author_text} et al. ({year}). {title}. {journal}."

        try:
            root = ET.fromstring(response.content)
            articles = root.findall(".//PubmedArticle")
            for article in articles:
                try:
                    pmid = article.findtext(".//PMID")
                    title = article.findtext(".//ArticleTitle", "")
                    title_lower = normalize_text(title)
                    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    journal = article.findtext(".//Journal/Title", "")
                    date = article.findtext(".//PubDate/Year") or article.findtext(".//PubDate/MedlineDate") or "N/A"

                    affs_raw = [aff.text.strip() for aff in article.findall(".//AffiliationInfo/Affiliation") if aff is not None]
                    aff_text = "; ".join(affs_raw)
                    aff_parts = list(chain.from_iterable([split_affiliations(a) for a in affs_raw]))

                    abstract_texts = article.findall(".//Abstract/AbstractText")
                    if abstract_texts:
                        abstract = "\n".join([elem.text.strip() if elem.text else "" for elem in abstract_texts])
                    else:
                        abstract = "N/A"

                    pub_types = [pt.text for pt in article.findall(".//PublicationType")]
                    pub_types_text = "; ".join(pub_types)
                    citation = build_citation(article)

                    score, reason = score_article(article, aff_parts, title_lower)
                    records.append({
                        "Title": title,
                        "Link": link,
                        "Journal": journal,
                        "Date": date,
                        "Publication Types": pub_types_text,
                        "Affiliations": aff_text,
                        "Abstract": abstract,
                        "Citation": citation,
                        "Score": score,
                        "Why": reason
                    })
                    parsed_ok += 1
                except Exception:
                    parsed_fail += 1
        except Exception:
            st.error("Failed to parse XML from PubMed.")

        df = pd.DataFrame(records).sort_values("Score", ascending=False)

        st.success(f"Found {len(id_list)} PMIDs. Successfully parsed {parsed_ok} articles. Failed to parse {parsed_fail}.")

        if not df.empty:
            st.dataframe(
                df[["Title", "Journal", "Date", "Publication Types", "Affiliations", "Score", "Why", "Citation", "Abstract"]],
                use_container_width=True
            )
            csv = df.to_csv(index=False)
            st.download_button("⬇️ Download CSV", data=csv, file_name="ranked_pubmed_results.csv", mime="text/csv")

            # -------------------- Summary Section --------------------
            st.header("📊 Summary Analysis")

            # Articles per Journal
            st.subheader("🔬 Articles per Journal")
            journal_counts = df['Journal'].value_counts()
            st.bar_chart(journal_counts)
            st.dataframe(journal_counts.reset_index().rename(columns={"index": "Journal", "Journal": "Count"}))

            # Renowned Institutions
            st.subheader("🏅 Renowned Institutions Mentioned")
            inst_counter_renowned = Counter()
            for aff in df["Affiliations"]:
                aff_parts = split_affiliations(aff)
                for inst in institutions:
                    for part in aff_parts:
                        if re.search(rf"\b{re.escape(inst.lower())}\b", part):
                            inst_counter_renowned[inst] += 1
            if inst_counter_renowned:
                inst_df_renowned = pd.DataFrame(inst_counter_renowned.items(), columns=["Institution", "Count"]).sort_values("Count", ascending=False)
                st.bar_chart(inst_df_renowned.set_index("Institution"))
                st.dataframe(inst_df_renowned)
            else:
                st.info("No renowned institutions were mentioned in the articles.")

            # All Institutions
            st.subheader("🌍 All Institutions Mentioned")
            all_affiliations = []
            for aff in df["Affiliations"]:
                all_affiliations.extend(split_affiliations(aff))
            inst_counter_all = Counter(all_affiliations)
            inst_df_all = pd.DataFrame(inst_counter_all.items(), columns=["Institution", "Count"]).sort_values("Count", ascending=False)
            st.bar_chart(inst_df_all.set_index("Institution"))
            st.dataframe(inst_df_all)

            # Publication Types
            st.subheader("📄 Articles per Publication Type")
            pubtype_list = list(chain.from_iterable([pt.split("; ") for pt in df["Publication Types"]]))
            pubtype_counts = pd.Series(pubtype_list).value_counts()
            st.bar_chart(pubtype_counts)
            st.dataframe(pubtype_counts.reset_index().rename(columns={"index": "Publication Type", 0: "Count"}))

            # Hot Keywords in Titles
            st.subheader("🔥 Articles with Hot Keywords in Title")
            hot_kw_counter = Counter()
            for title in df["Title"]:
                for kw in hot_keywords:
                    if kw in normalize_text(title):
                        hot_kw_counter[kw] += 1
            hot_df = pd.DataFrame(hot_kw_counter.items(), columns=["Hot Keyword", "Count"]).sort_values("Count", ascending=False)
            st.bar_chart(hot_df.set_index("Hot Keyword"))
            st.dataframe(hot_df)
        else:
            st.warning("No valid articles found to display.")
