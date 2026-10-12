import json
import tempfile
import unittest
from pathlib import Path
from job_radar_ai.html_posting import official_html
from job_radar_ai.sources import RetrievalError
from job_radar_ai.store import Store
from test_recovery import FixtureFetcher,page,TEXT,URL


class HTMLTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.store=Store(Path(t.name)/'state.sqlite3')
        self.job={'company':'Synthetic Employer','title':'Systems Lead','location':'Berlin, Germany','requisition_id':'REQ-42'}
        self.home='https://employer.example/careers'
        owner='<script type="application/ld+json">'+json.dumps({'@type':'Organization','name':self.job['company'],'url':'https://employer.example'})+'</script><a href="'+URL+'">Posting</a>'
        html='<link rel="canonical" href="'+URL+'"><nav>Unrelated footer text</nav><main><h1>Systems Lead</h1><p>Berlin, Germany</p><p>REQ-42</p><p>'+TEXT+'</p><script>Invented text hidden</script></main>'
        self.fetch=FixtureFetcher(self.store,{self.home:page(owner,self.home),URL:page(html,URL)})
    def test_verified_official_main_text_without_structured_jobposting(self):
        job=official_html(self.job,URL,self.home,self.fetch)[0]
        self.assertIn(TEXT.strip(),job['description']);self.assertNotIn('Invented text',job['description']);self.assertNotIn('footer',job['description'])
    def test_wrong_employer_country_role_requisition_or_missing_canonical_rejected(self):
        for key,value in [('company','Other'),('title','Different role'),('location','Berlin, Netherlands'),('requisition_id','OTHER')]:
            with self.assertRaises(RetrievalError):official_html({**self.job,key:value},URL,self.home,self.fetch)
        self.fetch.pages[URL]=page('<main><h1>Systems Lead</h1><p>Berlin, Germany REQ-42 '+TEXT+'</p></main>',URL)
        with self.assertRaises(RetrievalError):official_html(self.job,URL,self.home,self.fetch)
