import unittest
import numpy as np
from reverse_dcf import fcff_dcf, dcf_diagnostics, root_solver

class TestReverseDCF(unittest.TestCase):
    def test_wacc_must_exceed_terminal_growth(self):
        v=fcff_dcf(100,0.05,0.2,0.21,0.03,0.04,0.01,0.05,0.05,10,5,10)
        self.assertTrue(np.isnan(v))

    def test_positive_value_for_reasonable_inputs(self):
        v=fcff_dcf(100,0.05,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        self.assertTrue(np.isfinite(v)); self.assertGreater(v,0)

    def test_zero_shares_rejected(self):
        v=fcff_dcf(100,0.05,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,0)
        self.assertTrue(np.isnan(v))

    def test_growth_increases_value(self):
        low=fcff_dcf(100,0.03,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        high=fcff_dcf(100,0.07,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        self.assertGreater(high,low)

    def test_margin_increases_value(self):
        low=fcff_dcf(100,0.05,0.15,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        high=fcff_dcf(100,0.05,0.25,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        self.assertGreater(high,low)

    def test_higher_wacc_reduces_value(self):
        low=fcff_dcf(100,0.05,0.2,0.21,0.03,0.04,0.01,0.08,0.025,10,5,10)
        high=fcff_dcf(100,0.05,0.2,0.21,0.03,0.04,0.01,0.10,0.025,10,5,10)
        self.assertGreater(low,high)

    def test_diagnostics_reconcile_to_dcf(self):
        args=(100,0.05,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        value=fcff_dcf(*args)
        diag=dcf_diagnostics(*args)
        self.assertAlmostEqual(value,diag['value_per_share'],places=10)
        self.assertAlmostEqual(diag['enterprise_value'],diag['pv_explicit_fcff']+diag['pv_terminal_value'],places=10)

    def test_root_solver_finds_root(self):
        root=root_solver(lambda x:x*x-4,0,3)
        self.assertAlmostEqual(root,2.0,places=7)

    def test_bad_revenue_rejected(self):
        v=fcff_dcf(-100,0.05,0.2,0.21,0.03,0.04,0.01,0.09,0.025,10,5,10)
        self.assertTrue(np.isnan(v))

if __name__=="__main__": unittest.main()
