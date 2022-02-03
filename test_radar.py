import eleanor
from eleanor.radar import Radar

demo_camp_file = "demo/CSS0.json"


def test():
    my_camp = eleanor.Campaign.from_json(demo_camp_file, '/Users/tuckerely/39A_NavHelm/eleanor/eleanor/db')

    # my_camp.create_env(verbose=False)
    Radar(my_camp, ord_id=1)


if __name__ == '__main__':
    test()
