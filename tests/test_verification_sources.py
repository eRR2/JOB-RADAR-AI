"""Offline regressions for exact publisher HTML; all vacancies are synthetic."""
import unittest

from job_radar_ai.completion import vacancy_html
from job_radar_ai.html_posting import JobMain
from job_radar_ai.sources import RetrievalError


JOB = {
    'id': 'example:systems-owner-42',
    'url': 'https://careers.example.test/jobs/systems-owner-42',
    'title': 'Systems Owner',
    'company': 'Example Employer',
    'location': 'Example City',
}
DUTIES = (
    'Own system requirements and interface decisions across engineering teams. '
    'Review integration risks, agree verification plans and track release evidence. '
    'Requirements: practical systems engineering experience and ability to explain '
    'design decisions to product and validation teams.'
)


def publisher_page(body, canonical=JOB['url'], company=JOB['company']):
    return {
        'url': JOB['url'],
        'text': (
            '<!doctype html><html><head>'
            f'<link rel="canonical" href="{canonical}"></head><body>'
            f'<header>{company}</header>{body}</body></html>'
        ),
        'sha256': 'synthetic-page-hash',
    }


def region(tag='div', css='article-wrapper', title=JOB['title'], body=None):
    return (
        f'<{tag} class="{css}"><h1>{title}</h1>'
        '<div class="location">Example City</div>'
        f'<p>{DUTIES if body is None else body}</p></{tag}>'
    )


class ExactPublisherHtmlTests(unittest.TestCase):
    def test_exact_article_wrapper_retains_duties_and_requirements(self):
        full = vacancy_html(JOB, publisher_page(region()))
        self.assertIn(DUTIES, full['description'])
        self.assertEqual(full['title'], JOB['title'])
        self.assertEqual(full['source_url'], JOB['url'])

    def test_self_closing_void_elements_do_not_end_job_root(self):
        for element in ('<hr/>', '<br/>', '<img src="badge.svg"/>'):
            with self.subTest(element=element):
                page = publisher_page(
                    '<main><h1>Systems Owner</h1>' + element +
                    f'<p>{DUTIES}</p></main>'
                )
                parser = JobMain()
                parser.feed(page['text'])
                self.assertEqual(parser.count, 1)
                self.assertIn(DUTIES, ''.join(parser.parts))
                self.assertIn(DUTIES, vacancy_html(JOB, page)['description'])

    def test_application_form_and_navigation_are_not_role_evidence(self):
        page = publisher_page(
            '<main><h1>Systems Owner</h1>'
            '<nav>Browse all unrelated career categories</nav>'
            '<form><label>Upload personal records and accept marketing</label>'
            '<textarea>Unrelated application form answer</textarea></form>'
            f'<p>{DUTIES}</p>'
            '<footer>Corporate newsletter subscription</footer></main>'
        )
        description = vacancy_html(JOB, page)['description']
        self.assertIn(DUTIES, description)
        self.assertNotIn('personal records', description)
        self.assertNotIn('application form answer', description)
        self.assertNotIn('unrelated career categories', description)
        self.assertNotIn('newsletter subscription', description)

    def test_conflicting_canonical_is_rejected(self):
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, publisher_page(region(), canonical='/jobs/another-role'))

    def test_multiple_job_regions_are_rejected(self):
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, publisher_page(region() + region()))

    def test_wrong_published_title_is_rejected(self):
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, publisher_page(region(title='Different Position')))

    def test_wrong_published_employer_is_rejected(self):
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, publisher_page(region(), company='Other Employer'))

    def test_title_only_region_is_not_a_complete_description(self):
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, publisher_page(region(body='')))

    def test_general_careers_homepage_is_not_the_exact_vacancy(self):
        page = publisher_page(
            '<main><h1>Careers at Example Employer</h1>'
            '<p>Explore our departments and join our teams. '
            'We welcome talented people with varied backgrounds and interests. '
            'Browse the careers catalogue to discover future possibilities.</p></main>'
        )
        with self.assertRaises(RetrievalError):
            vacancy_html(JOB, page)


if __name__ == '__main__':
    unittest.main()
