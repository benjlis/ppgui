import streamlit as st
import pandas as pd
import psycopg2
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from st_aggrid.shared import JsCode

VERSION = 'Beta-v0.3'
TITLE = f'Pandemic Program Document Search'
SEARCH_LABEL = "Search:" 
SEARCH_PLACEHOLDER = "Full-text search across document collection"
SEARCH_HELP = "Use double quotes for phrases, OR for logical or, and - for \
logical not."

st.set_page_config(page_title=TITLE, layout="wide")
st.image('assets/covid19-image.png', use_column_width='always')
st.title(TITLE)
st.caption(VERSION)

#
# Database functions, initializatons and queries
#
@st.cache_resource
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])


# Execute query.
@st.cache_data(ttl="1d")
def run_query(query):
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


conn = init_connection()
doc_qry = """
select count(page_id) hits, doc_id, title, pg_cnt, 
       dc_organization, dc_username, pdf_url
    from covid19_muckrock.docpages_authorized
    where full_text @@ websearch_to_tsquery('english', '{search}') 
    group by doc_id, title, pg_cnt, pdf_url, 
             dc_organization, dc_username
    order by count(page_id) desc
"""
# TBD - update
pg_qry = """
select d.pg, 
       ts_headline('english', 
                   regexp_replace(d.body, '\r|\n', ' ', 'g'), 
                   websearch_to_tsquery('english', '{search}'), 
                   'maxfragments=6') snippet 
    from covid19_muckrock.docpages_authorized d 
    where doc_id = {doc_id} and 
          full_text @@ websearch_to_tsquery('english', '{search}') 
    order by d.pg;
"""

#
# streamlit-aggrid initializations and configurations
#
response = {}
css_fix = {"#gridToolBar": {"padding-bottom": "0px !important"}}
gb = GridOptionsBuilder()
gb.configure_default_column(resizable=True, filterable=True, 
                            sortable=True, editable=True)
gb.configure_column(field="hits", header_name="Hits", width=80)
gb.configure_column(field="doc_id", header_name="ID", width=100)
gb.configure_column(field="title", header_name="Title", width=420, 
                    tooltipField="title")
gb.configure_column(field="pg_cnt", header_name="Pages", width=80)
gb.configure_column(field="dc_organization", header_name="Organization", width=140)
gb.configure_column(field="dc_username", header_name="Contributor", width=160,
                    tooltipField="dc_username")
cell_renderer=JsCode("""
        class UrlCellRenderer {
          init(params) {
            this.eGui = document.createElement('a');
            this.eGui.innerText = params.value;
            this.eGui.setAttribute('href', params.value);
            this.eGui.setAttribute('style', "text-decoration:none");
          }
          getGui() {
            return this.eGui;
          }
        }
    """)
gb.configure_column(field="pdf_url", header_name="URL", 
                    cellRenderer=cell_renderer, width=700,
                    tooltipField="pdf_url")
gb.configure_grid_options(editable=True)
# Note: some weirdness with pagination in the release we're using
gb.configure_pagination(enabled=True, paginationPageSize=10)
gb.configure_selection(selection_mode='single', groupSelectsChildren=False)
go = gb.build()



@st.cache_data
def convert_df(df):
    # IMPORTANT: Cache the conversion to prevent computation on every rerun
    return df.to_csv().encode('utf-8')

# Search across docs
srchstr = st.text_input(label=SEARCH_LABEL,
                        placeholder=SEARCH_PLACEHOLDER,
                        help=SEARCH_HELP)
if 'running' not in st.session_state:
    st.session_state.running = True
else:
    doc_df = pd.read_sql_query(doc_qry.format(search=srchstr), conn)
    if doc_df.empty:
        st.markdown(f"Your search `{srchstr}` did not match any documents")
    else:
        csv = convert_df(doc_df)
        st.download_button(label='CSV Download', data=csv,
                           file_name='pp.csv', mime='text/csv')
        # st.markdown(doc_df.to_markdown(index=False))
        response = AgGrid(doc_df, gridOptions=go, 
                          allow_unsafe_jscode=True,
                          updateMode=GridUpdateMode.SELECTION_CHANGED, 
                          height=500, custom_css=css_fix)


# Highlights from pages  
if 'running' in st.session_state and response:      
    selected = response['selected_rows']
    if selected:
        doc_id = selected[0]["doc_id"]
        title = selected[0]["title"]
        pg_df = pd.read_sql_query(pg_qry.format(search=srchstr, 
                                                doc_id=doc_id), conn)
        st.markdown(f'References to _{srchstr}_ in **{title}** ({doc_id}):')
        st.markdown(pg_df.to_markdown(index=False), 
                    unsafe_allow_html=True)
        
# Footer
st.subheader("About")
with open("./assets/pp.md", "r") as f:
    markdown_text = f.read()
st.markdown(markdown_text)
st.subheader("Funding")
logo, description, _ = st.columns([1,2,2])
with logo:
    st.image('assets/nhprc-logo.png')
with description:
    """
Funding for the COVID-19 Archive has been provided by an archival
project grant from the [National Historical Publications & Records
Commission (NHPRC)](https://www.archives.gov/nhprc). 
    """