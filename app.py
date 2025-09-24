import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
from collections import Counter
import calendar

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
journals = [j.strip().lower() for j in journal_input.splitlines() if j.strip()]

default_institutions = "\n".join([
    "Harvard", "Oxford", "Mayo", "NIH", "Stanford",
    "UCSF", "Yale", "Cambridge", "Karolinska Institute", "Johns Hopkins"
])
inst_input = st.text_area("Renowned Institutions (one per line)", value=default_institutions, height=150)
institutions = [i.strip().lower() for i in inst_input.splitlines() if i.strip()]

default_summary = "\n".join([
    "Harvard",
    "Stanford",
    "Massachusetts Institute of Technology",
    "University of Cambridge",
    "University of Oxford",
    "University of California, Berkeley",
    "Princeton University",
    "Yale University",
    "University of Chicago",
    "Columbia",
    "California Institute of Technology",
    "University College London",
    "ETH Zurich",
    "Imperial College London",
    "University of Toronto",
    "Tsinghua University",
    "Peking University",
    "National University of Singapore",
    "University of Melbourne",
    "University of Tokyo",
    "Kyoto University",
    "Seoul National University",
    "University of Hong Kong",
    "University of British Columbia",
    "University of Sydney",
    "University of Edinburgh",
    "University of Manchester",
    "Ludwig Maximilian University of Munich",
    "University of Copenhagen",
    "University of Amsterdam",
    "University of Zurich",
    "McGill University",
    "King's College London",
    "University of Illinois Urbana-Champaign",
    "École Polytechnique Fédérale de Lausanne",
    "University of Pennsylvania",
    "Cornell University",
    "Johns Hopkins",
    "Duke University",
    "University of California, Los Angeles",
    "University of Michigan",
    "University of Texas at Austin",
    "Washington University in St. Louis",
    "University of California, San Diego",
    "University of California, Davis",
    "University of Washington",
    "University of Wisconsin–Madison",
    "New York University",
    "University of North Carolina at Chapel Hill",
    "National Taiwan University"
])
summary_input = st.text_area(
    "Institutions for Summary Analysis (one per line)",
    value=default_summary,
    height=200
)
summary_institutions = [i.strip().lower() for i in summary_input.splitlines() if i.strip()]

default_keywords = "\n".join([
    "glp-1", "semaglutide", "tirzepatide", "ai", "machine learning", "telemedicine"
])
hot_input = st.text_area("Hot Keywords (one per line)", value=default_keywords, height=100)
hot_keywords = [k.strip().lower() for k in hot_input.splitlines() if k.strip()]

max_results = st.number_input("Max number of articles to fetch", min_value=10, max_value=1000, value=250, step=10)

# -------------------- Utility Functions --------------------
def normalize_text(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()

INSTITUTION_KEYWORDS = [
    "univ", "university", "hospital", "clinic", "institute",
    "college", "center", "centre", "school", "department",
    "laboratory", "lab"
]

def split_affiliations(raw_aff, institution_list):
    parts = (raw_aff or "").split(";")
    filtered = []
    for part in parts:
        text = normalize_text(part)
        if len(text) < 5 or re.fullmatch(r"\d+", text):
            continue
        if any(inst in text for inst in institution_list):
            filtered.append(text)
            continue
        if any(kw in text for kw in INSTITUTION_KEYWORDS):
            filtered.append(text)
    return list(dict.fromkeys(filtered))

def match_institution(text, institution_list):
    text = normalize_text(text)
    return any(re.search(rf"\b{re.escape(inst)}\b", text) for inst in institution_list)

def month_to_num(m):
    if not m:
        return None
    m = m.strip()
    if m.isdigit():
        return m.zfill(2)
    # try month abbreviations (Jan, Feb...) or full names
    try:
        # normalize to first 3 letters titlecase, match against calendar.month_abbr
        m3 = m[:3].title()
        for i in range(1,13):
            if calendar.month_abbr[i] == m3 or calendar.month_name[i].lower().startswith(m.lower()):
                return str(i).zfill(2)
    except:
        pass
    return None

# -------------------- Scoring & Helpers --------------------
def score_article(article, aff_parts, title_text):
    score, reasons = 0, []
    journal = (article.findtext(".//Journal/Title","") or "").lower()
    if any(j in journal for j in journals):
        score+=2; reasons.append("High-impact journal (+2)")
    pub_types = [ (pt.text or "").lower() for pt in article.findall(".//PublicationType") ]
    valued = ["randomized controlled trial","systematic review","meta-analysis","guideline","practice guideline"]
    if any(pt in valued for pt in pub_types):
        score+=2; reasons.append("Valued publication type (+2)")
    if len(article.findall(".//Author"))>=5:
        score+=1; reasons.append("Multiple authors (+1)")
    if any(match_institution(aff, institutions) for aff in aff_parts):
        score+=1; reasons.append("Prestigious institution (+1)")
    if any(kw in title_text for kw in hot_keywords):
        score+=2; reasons.append("Hot keyword in title (+2)")
    if article.find(".//GrantList") is not None:
        score+=2; reasons.append("Has research funding (+2)")
    return score, "; ".join(reasons)

def build_citation(article):
    authors = article.findall(".//Author")
    if authors:
        first = authors[0]
        last = first.findtext("LastName","")
        init = first.findtext("Initials","")
        auth = f"{last} {init}" if last else "Unknown Author"
    else:
        auth = "Unknown Author"
    # try several places for year
    year = article.findtext(".//PubDate/Year") or article.findtext(".//PubDate/MedlineDate") or "n.d."
    title = (article.findtext(".//ArticleTitle","") or "").strip()
    journal = article.findtext(".//Journal/Title","") or ""
    return f"{auth} et al. ({year}). {title}. {journal}."

# -------------------- Search and Processing --------------------
if st.button("🔎 Run PubMed Search"):
    with st.spinner("Fetching articles..."):
        # ESearch
        try:
            r = requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db":"pubmed","retmax":str(max_results),"retmode":"json","term":query},
                timeout=30
            )
            id_list = r.json().get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            st.error(f"ESearch failed: {e}")
            id_list = []

        if not id_list:
            st.warning("No PMIDs found for this query.")
        else:
            # EFetch
            try:
                response = requests.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params={"db":"pubmed","id":",".join(id_list),"retmode":"xml"},
                    timeout=60
                )
            except Exception as e:
                st.error(f"EFetch failed: {e}")
                response = None

            parsed_ok = parsed_fail = 0
            records = []

            if response is not None:
                try:
                    root = ET.fromstring(response.content)
                    for art in root.findall(".//PubmedArticle"):
                        try:
                            pmid = art.findtext(".//PMID") or ""
                            title = art.findtext(".//ArticleTitle","") or ""
                            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                            journal = art.findtext(".//Journal/Title","") or ""
                            date = art.findtext(".//PubDate/Year") or art.findtext(".//PubDate/MedlineDate") or "N/A"

                            raw_affs = [a.text for a in art.findall(".//AffiliationInfo/Affiliation") if a.text]
                            aff_text = "; ".join(raw_affs)
                            aff_parts = split_affiliations(aff_text, institutions)

                            abstract_elems = art.findall(".//Abstract/AbstractText")
                            abstract = "\n".join(e.text.strip() for e in abstract_elems if e.text) if abstract_elems else "N/A"

                            pub_types = [pt.text for pt in art.findall(".//PublicationType") if pt.text]
                            pub_types_text = "; ".join(pub_types)
                            citation = build_citation(art)

                            # --- PubMed Entry Date (full) ---
                            pubmed_entry_date = "N/A"
                            # try to find the PubMedPubDate with PubStatus="pubmed"
                            node = art.find('.//PubmedData/History/PubMedPubDate[@PubStatus="pubmed"]')
                            if node is None:
                                # fallback to any PubMedPubDate under History
                                node = art.find('.//PubmedData/History/PubMedPubDate')
                            if node is not None:
                                y = node.findtext('Year')
                                m = node.findtext('Month')
                                d = node.findtext('Day')
                                mn = month_to_num(m)
                                if y and mn and d:
                                    pubmed_entry_date = f"{mn}/{d.zfill(2)}/{y}"
                                elif y and mn:
                                    pubmed_entry_date = f"{mn}/{y}"
                                elif y:
                                    pubmed_entry_date = y

                            # --- Mesh Terms ---
                            mesh_terms = []
                            for desc in art.findall(".//MeshHeading/DescriptorName"):
                                if desc is not None and (desc.text or "").strip():
                                    mesh_terms.append(desc.text.strip())
                            # also include qualifier names (optional)
                            for qual in art.findall(".//MeshHeading/QualifierName"):
                                if qual is not None and (qual.text or "").strip():
                                    # qualifier could duplicate descriptor; include optionally
                                    pass

                            # --- Chemical Substances ---
                            chemicals = [c.text.strip() for c in art.findall(".//Chemical/NameOfSubstance") if c.text and c.text.strip()]

                            # --- Author Keywords ---
                            keywords_set = set()
                            for kw in art.findall(".//Keyword"):
                                if kw is not None and (kw.text or "").strip():
                                    keywords_set.add(kw.text.strip())
                            for kw in art.findall(".//KeywordList/Keyword"):
                                if kw is not None and (kw.text or "").strip():
                                    keywords_set.add(kw.text.strip())
                            keywords = sorted(keywords_set)

                            # --- Genes / Proteins ---
                            genes_set = set()
                            for g in art.findall(".//GeneSymbol"):
                                if g is not None and (g.text or "").strip():
                                    genes_set.add(g.text.strip())
                            for g in art.findall(".//Gene"):
                                if g is not None and (g.text or "").strip():
                                    genes_set.add(g.text.strip())
                            genes = sorted(genes_set)

                            score, reason = score_article(art, aff_parts, normalize_text(title))

                            records.append({
                                "PMID": pmid,
                                "Title": title,
                                "Link": link,
                                "Journal": journal,
                                "Date": date,
                                "Publication Types": pub_types_text,
                                "Affiliations": aff_text,
                                "AffParts": aff_parts,
                                "Abstract": abstract,
                                "Citation": citation,
                                "Score": score,
                                "Why": reason,
                                "PubMed Entry Date": pubmed_entry_date,
                                "Mesh Terms": "; ".join(mesh_terms),
                                "Chemical Substances": "; ".join(chemicals),
                                "Author Keywords": "; ".join(keywords),
                                "Genes/Proteins": "; ".join(genes)
                            })
                            parsed_ok += 1
                        except Exception:
                            parsed_fail += 1
                except Exception:
                    st.error("Failed to parse XML from PubMed.")

            df = pd.DataFrame(records).sort_values("Score", ascending=False)
            st.success(f"Found {len(id_list)} PMIDs. Parsed {parsed_ok}, failed {parsed_fail}.")

            if not df.empty:
                # show dataframe (hide AffParts internal column)
                show_cols = [
                    "Title","Journal","Date","Publication Types","Affiliations",
                    "Score","Why","Citation","Abstract",
                    "PubMed Entry Date","Mesh Terms","Chemical Substances","Author Keywords","Genes/Proteins","Link"
                ]
                st.dataframe(df.drop(columns="AffParts")[show_cols], use_container_width=True)
                st.download_button(
                    "⬇️ Download CSV",
                    data=df.drop(columns="AffParts").to_csv(index=False),
                    file_name="ranked_pubmed_results.csv",
                    mime="text/csv"
                )

                st.header("📊 Summary Analysis")

                # 🔬 Articles per Journal
                st.subheader("🔬 Articles per Journal")
                jc = df['Journal'].value_counts()
                st.bar_chart(jc)
                st.dataframe(jc.reset_index().rename(columns={"index":"Journal","Journal":"Count"}))

                # 🏅 Renowned Institutions Summary
                st.subheader("🏅 Renowned Institutions Summary")
                ren_counter = Counter()
                for parts in df["AffParts"]:
                    match = [inst for inst in institutions if any(inst in p for p in parts)]
                    if match:
                        for inst in set(match):
                            ren_counter[inst] += 1
                    else:
                        ren_counter["Others"] += 1
                ren_df = (
                    pd.DataFrame.from_dict(ren_counter, orient="index", columns=["Count"])
                      .rename_axis("Institution")
                      .sort_values("Count", ascending=False)
                )
                st.bar_chart(ren_df)
                st.dataframe(ren_df.reset_index())

                # Selected Institutions Summary
                st.subheader("Selected Institutions Summary")
                sel_counter = Counter()
                for parts in df["AffParts"]:
                    match = [inst for inst in summary_institutions if any(inst in p for p in parts)]
                    if match:
                        for inst in set(match):
                            sel_counter[inst] += 1
                    else:
                        sel_counter["Others"] += 1
                sel_df = (
                    pd.DataFrame.from_dict(sel_counter, orient="index", columns=["Count"])
                      .rename_axis("Institution")
                      .sort_values("Count", ascending=False)
                )
                st.bar_chart(sel_df)
                st.dataframe(sel_df.reset_index())

                # 📄 Publication Types
                st.subheader("📄 Articles per Publication Type")
                pt = df["Publication Types"].str.split("; ").explode().value_counts()
                st.bar_chart(pt)
                st.dataframe(pt.reset_index().rename(columns={"index":"Publication Type",0:"Count"}))

                # 🔥 Hot Keywords in Titles
                st.subheader("🔥 Articles with Hot Keywords in Title")
                hk = Counter()
                for title in df["Title"]:
                    t = normalize_text(title)
                    for kw in hot_keywords:
                        if kw in t:
                            hk[kw] += 1
                hk_df = (
                    pd.DataFrame.from_dict(hk, orient="index", columns=["Count"])
                      .rename_axis("Hot Keyword")
                      .sort_values("Count", ascending=False)
                )
                st.bar_chart(hk_df)
                st.dataframe(hk_df.reset_index())
            else:
                st.warning("No valid articles to display.")
