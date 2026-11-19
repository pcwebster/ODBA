"""Offline browser QA. Run with Playwright and an installed Chromium."""
import argparse
from pathlib import Path
import os
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('html', type=Path)
parser.add_argument('--content', action='store_true',
                    help='Load local HTML directly when managed browsers restrict file URLs')
args = parser.parse_args()
source = args.html.resolve()

def load(page):
    if args.content:
        page.set_content(source.read_text(encoding='utf-8'), wait_until='load')
    else:
        page.goto(source.as_uri())

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=os.environ.get('CHROMIUM', '/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
    desktop = browser.new_page(viewport={'width': 1280, 'height': 1000}, offline=True)
    errors = []
    desktop.on('pageerror', lambda error: errors.append(str(error)))
    load(desktop)
    expect(desktop.get_by_role('heading',name='Operations & maintenance')).to_be_visible()
    expect(desktop.locator('#ocontext')).to_have_text(
        'Funding FY2025 · O&M Title + Indefinite Accounts · as-published total obligational authority (TOA)'
    )
    first_amount = desktop.locator('#ocompare .ocrow-head').first
    expect(first_amount.locator('span')).to_have_text('FY2025 · PB25 · President’s Budget request · TOA')
    expect(first_amount.locator('strong')).to_have_text('$338.098474B')
    expect(desktop.locator('#ocompare')).to_contain_text('$338.098474B')
    expect(desktop.locator('#ocompare')).to_contain_text('$338.459009B')
    expect(desktop.locator('#ocompare')).to_contain_text('$342.358161B')
    expect(desktop.locator('#ocompare')).to_contain_text('$350.101702B')
    expect(desktop.locator('#oguide')).to_contain_text('$41.3M')
    desktop.locator('#oextra summary').click()
    expect(desktop.locator('#oother')).to_contain_text('$3.940452B')
    desktop.locator('#ofiscal').select_option('2026')
    expect(desktop.locator('#oother')).to_contain_text('FY2026 · PB26 · Reconciliation request · TOA')
    expect(desktop.locator('#oother')).to_contain_text('$22.708023B')
    expect(desktop.locator('#oother')).to_contain_text('$19.991335B')
    desktop.locator('#ofiscal').select_option('2024')
    expect(desktop.locator('#oguide')).to_contain_text('not an enacted or actual amount')
    desktop.locator('#ovintage').select_option(label='PB25')
    desktop.locator('#osearch').fill('totally missing test')
    expect(desktop.locator('#ocount')).to_contain_text('No matching')
    desktop.locator('#osearch').fill('')
    expect(desktop.locator('#ocount')).to_contain_text('20 of 434')
    desktop.locator('#omore').click()
    expect(desktop.locator('#ocount')).to_contain_text('40 of 434')
    desktop.locator('#oaccount').select_option('0100D')
    desktop.locator('#osearch').fill('490')
    result=desktop.locator('#olines details').first
    result.locator('summary').click()
    expect(result).to_contain_text('FY2024 · PB25 · CR-adjusted request · TOA')
    expect(result).to_contain_text('−$1,288.238M')
    assert '#page=' in result.get_by_role('link').get_attribute('href')
    desktop.get_by_role('button',name='Department trends').click()
    desktop.locator('#dep').select_option('Defense-Wide')
    expect(desktop.locator('#hcontext')).to_contain_text('−$10.636B')
    desktop.get_by_role('button',name='Year-over-year variance').click()
    expect(desktop.locator('#vy option[value="1948"]')).to_have_count(0)
    desktop.locator('#vy').select_option('1991')
    expect(desktop.locator('#vt')).to_contain_text('Unavailable')
    desktop.get_by_role('button',name='Agency & program').click()
    desktop.locator('#at tbody button').first.click()
    expect(desktop.locator('#detail')).to_be_visible()
    desktop.get_by_role('button',name='Pipeline & sources').click()
    expect(desktop.locator('#pc')).to_contain_text('1238 verified detail rows')
    assert not errors, errors
    phone=browser.new_page(viewport={'width':360,'height':780},is_mobile=True,has_touch=True,offline=True)
    phone.on('pageerror', lambda error: errors.append(str(error)))
    load(phone)
    expect(phone.locator('#ocompare')).to_be_visible()
    assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
    phone.locator('#osearch').fill('0130D')
    phone.locator('#olines details summary').first.tap()
    pinned_amounts = phone.locator('#olines > details[open] > dl.olamount')
    expect(pinned_amounts).to_be_visible()
    expect(pinned_amounts).to_contain_text('FY2025 · PB27 · Actuals as reported (printed lane) · TOA')
    assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    print('Chromium offline smoke passed: exact FY25 stages, FY26 supplemental bases, FY24 CR caution, filters, pagination, signed drilldown, source page, legacy views, and mobile layout.')
