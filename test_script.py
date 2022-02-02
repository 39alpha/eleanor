import eleanor
from eleanor.helmsman import main
demo_camp_file = "demo/CSS0.json"
my_camp = eleanor.Campaign.from_json(demo_camp_file, '/path/to/db')
my_camp.create_env(verbose=False)

eleanor.Navigator(my_camp)

main(my_camp, 1)
