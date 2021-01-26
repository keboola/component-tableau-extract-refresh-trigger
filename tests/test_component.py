'''
Created on 12. 11. 2018

@author: esner
'''
import mock
import os
import unittest
from freezegun import freeze_time

from component import Component


class TestComponent(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                            'data_test')
        os.environ["KBC_DATADIR"] = path

    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {'KBC_DATADIR': './non-existing-dir'})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()

    def test_fails_with_server_unavailable_and_retries(self):
        with self.assertRaises(SystemExit) as cm:
            comp = Component()
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
