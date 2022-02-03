import eleanor
from eleanor.helmsman import main
demo_camp_file = "demo/CSS0.json"

def test():
    my_camp = eleanor.Campaign.from_json(demo_camp_file, '/Users/tuckerely/39A_NavHelm/eleanor/eleanor/db')
    my_camp.create_env(verbose=False)
    eleanor.Navigator(my_camp)
    main(my_camp, 1)


if __name__ == '__main__':
    test()