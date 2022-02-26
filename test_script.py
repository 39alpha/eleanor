import eleanor
demo_camp_file = "demo/CSS0.json"

def test():
    from os import environ
    data0dir = "test/data/db"
    my_camp = eleanor.Campaign.from_json(demo_camp_file, data0dir)
    my_camp.create_env(verbose=False)
    eleanor.Navigator(my_camp)
    eleanor.Helmsman(my_camp, 1)


if __name__ == '__main__':
    test()
