import eleanor
from eleanor.radar_grid import Radar

demo_camp_file = "demo/CSS0.json"


def test():
    my_camp = eleanor.Campaign.from_json(demo_camp_file, '/Users/tuckerely/39A_NavHelm/eleanor/eleanor/db')

    # ### test gird
    # ### scalar, gird, or condition
    # color_condition = ['solid', '{CO2_e} > -2.5']
    color_condition = ['solid', '{calcite_e} >= -1000']
    # color_condition = ['grid', ['CO2_e', 'Ca_e']]
    # color_condition = ['color', 'black']
    # color_condition = ['species', '{CO2_e} > -2.5']

    vars = ['dpH = (-{H+_e}) - (-{H+_v})',
            '{CO2_e}',
            '{T_cel_v}',
            '{P_bar_v}',
            '{Ca_v}',
            '{Ca_e}',
            '{HCO3-_e}',
            '{dolomite_e}'
            ]

    description = " gird figure test"

    Radar(my_camp, vars, color_condition, description, ord_id=1, limit=1000, where=None,
          add_analytics=False)


if __name__ == '__main__':
    test()
