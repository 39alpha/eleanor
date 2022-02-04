import eleanor
from eleanor.radar_xyz import Radar

demo_camp_file = "demo/CSS0.json"


def test():
    my_camp = eleanor.Campaign.from_json(demo_camp_file, '/Users/tuckerely/39A_NavHelm/eleanor/eleanor/db')

    # my_camp.create_env(verbose=False)

    x_sp = 'dpH = (-{H+_e}) - (-{H+_v})'
    y_sp = '{CO2_e}'
    z_sp = '{T_cel_v}'

    # where = 'CO2_e > -2.5'
    where = None
    env_dat = []
    description = " figure tests"

    Radar(my_camp, x_sp, y_sp, z_sp, description, ord_id=1,
          where=where, transparent=False, add_analytics=False)


if __name__ == '__main__':
    test()
