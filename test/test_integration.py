import unittest
import eleanor

class TestCampaign_to_Orders(unittest.TestCase):
    """
    Tests integration between Campaign, Navigator and Helmsmen Classes
    """

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_campaign_to_orders(self):
        """
        Confirm that the demo campaign CSS0 can be generated and converted into orders
        """
        demo_camp_file = "demo/CSS0.json"
        my_camp = eleanor.Campaign.from_json(demo_camp_file)
        my_camp.create_env()

        eleanor.Navigator(my_camp)
        with my_camp.working_directory():
            this_conn = eleanor.hanger.db_comms.establish_database_connection(my_camp)
        order_num = eleanor.hanger.db_comms.get_order_number(this_conn)
        self.assertTrue(order_num == 1)
        # Need to clean this up by removing CSSO directory




