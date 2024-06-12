import numpy as np
import shutil
import random
from eleanor import Campaign, Navigator, Helmsman
from os.path import dirname, join, realpath

DIR = dirname(realpath(__file__))


def main():
    print(DIR)

    shutil.rmtree(join(DIR, "regression-testing"), ignore_errors=True)

    random.seed(2024)
    np.random.seed(2024)

    camp = Campaign.from_json(join(DIR, "campaign.json"), join(DIR, "db"))
    camp.create_env(verbose=True)

    Navigator(camp, quiet=False)
    Helmsman(camp, num_cores=1, keep_every_n_files=1)


if __name__ == '__main__':
    main()
