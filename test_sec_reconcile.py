import unittest
from sec_reconcile import pick_fact, fetch_sec_facts

class TestSECReconcile(unittest.TestCase):
    def test_pick_latest_annual_period(self):
        payload={"facts":{"us-gaap":{"RevenueFromContractWithCustomerExcludingAssessedTax":{"units":{"USD":[
            {"form":"10-K","fp":"FY","end":"2023-09-30","filed":"2023-11-03","val":100},
            {"form":"10-K","fp":"FY","end":"2024-09-28","filed":"2024-11-01","val":120},
            {"form":"10-Q","fp":"Q1","end":"2025-03-29","filed":"2025-05-02","val":40}]}}}}}
        f=pick_fact(payload,["RevenueFromContractWithCustomerExcludingAssessedTax"])
        self.assertEqual(f["value"],120)
        self.assertEqual(f["period_end"],"2024-09-28")
    def test_prefers_first_available_tag(self):
        payload={"facts":{"us-gaap":{"SalesRevenueNet":{"units":{"USD":[{"form":"10-K","fp":"FY","end":"2024-12-31","filed":"2025-02-01","val":55}]}}}}}
        self.assertEqual(pick_fact(payload,["NoSuchTag","SalesRevenueNet"])["value"],55)
    def test_requires_user_agent(self):
        with self.assertRaises(ValueError): fetch_sec_facts("AAPL","")
    def test_unknown_ticker_requires_verified_cik(self):
        with self.assertRaises(ValueError): fetch_sec_facts("NOTREAL","Research contact@example.com")

if __name__ == "__main__": unittest.main()
