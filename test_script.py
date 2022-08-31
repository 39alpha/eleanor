import eleanor
# import cProfile
# import pstats
demo_camp_file = "demo/CSS0.json"

# PROFILER = cProfile.Profile()

def test():
    data0dir = "test/data/db"
    my_camp = eleanor.Campaign.from_json(demo_camp_file, data0dir)
    my_camp.create_env(verbose=False)
    eleanor.Navigator(my_camp)
    eleanor.Helmsman(my_camp, 1)


if __name__ == '__main__':
    test()
    # stats = pstats.Stats(PROFILER).sort_stats('ncalls')
    # stats.print_stats()
