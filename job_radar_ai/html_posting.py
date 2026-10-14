"""Conservative job-specific HTML fallback; never model-generated descriptions."""
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
from .sources import TextParser,exact,RetrievalError
from .ats import ownership

VOID_TAGS={'br','hr','meta','link','img','input','source','wbr','area','base','col','embed','param','track'}


class JobMain(HTMLParser):
    def __init__(self):
        super().__init__();self.depth=0;self.root=None;self.count=0;self.parts=[];self.title=[];self.h1=0;self.hidden=0;self.canonical=''
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='link' and 'canonical' in attrs.get('rel','').split():self.canonical=attrs.get('href','')
        if tag not in VOID_TAGS:self.depth+=1
        classes=set(attrs.get('class','').split())
        if self.root is None and (tag in ('main','article') or attrs.get('itemprop')=='description' or classes & {'article-mainbody','article-wrapper','job-description','jobDescription','job__description'}):self.root=self.depth;self.count+=1
        if tag=='h1':self.h1+=1
        if self.root:
            if tag in ('script','style','nav','footer','header','form'):self.hidden+=1
            if tag in ('p','div','li','br','h1','h2','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag=='h1':self.h1=max(0,self.h1-1)
        if self.root:
            if tag in ('script','style','nav','footer','header','form'):self.hidden=max(0,self.hidden-1)
            if tag not in VOID_TAGS and self.depth==self.root:self.root=None
        if tag not in VOID_TAGS:self.depth=max(0,self.depth-1)
    def handle_data(self,data):
        if self.h1 and not self.hidden:self.title.append(data)
        if self.root and not self.hidden:
            self.parts.append(data)


def official_html(job,url,employer_url,fetcher):
    if not employer_url or urlsplit(url).hostname!=urlsplit(employer_url).hostname:
        raise RetrievalError('unverified','HTML fallback requires an exact official employer host.')
    # Independent employer Organization and exact posting link, not AI ownership prose.
    company=ownership({'url':url,'employer_url':employer_url},fetcher)
    page=fetcher.get(url);parser=JobMain();parser.feed(page['text'])
    text=''.join(parser.parts).strip();title=''.join(parser.title).strip()
    if parser.count!=1 or urljoin(page['url'],parser.canonical)!=page['url'] or not parser.canonical:
        raise RetrievalError('unverified','A unique job-specific main region and matching published canonical link are required.')
    if exact(title)!=exact(job.get('title','')) or exact(company)!=exact(job.get('company','')):
        raise RetrievalError('unverified','Official HTML employer/title conflicts with the observed vacancy.')
    location=job.get('location','')
    if not location or exact(location) not in exact(text):
        raise RetrievalError('unverified','Actual HTML does not state the exact advertised locality/country.')
    requisition=job.get('requisition_id','')
    if requisition and exact(requisition) not in exact(text):
        raise RetrievalError('unverified','Known requisition is absent from actual HTML.')
    if not 100<=len(text)<=60000:
        raise RetrievalError('incomplete','Complete job-specific HTML text is outside safe bounds; no truncation.')
    return [{'title':title,'company':company,'location':location,'description':text,'requisition_id':requisition,'source_url':page['url'],'evidence':page}]
