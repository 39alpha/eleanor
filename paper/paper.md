---
title: 'Eleanor: A Python package large-scale aqueous chemical modeling'
tags:
  - Python
  - aqueous
  - chemistry
  - eq3/6
  - geochemistry
authors:
  - name: Team 0
    affiliation: "1"
affiliations:
 - name: 39 Alpha Research, Tempe, AZ USA
   index: 1
date: 27 January 2023
bibliography: paper.bib
---

# TODO

- [ ] Make repo public

Currently on JOSS, under ‘geochemistry’
https://joss.theoj.org/papers/10.21105/joss.03314 

# Summary

Describing the high-level functionality and purpose of the software for a diverse, non-specialist audience.

Calculating the chemical compositions and properties of water-based solutions is an essential technique in geochemistry, ecology, astrobiology, engineering, and many other disciplines. Tools and techniques for estimating the proper parameters and solving the appropriate systems of equations have existed for decades (cite). However, existing tools were developed when computational speed was limiting in a way that it no longer is. `Eleanor` is a python package that parallelizes the execution of the geochemical modeling software EQ3/6, a reliable and longstanding workhorse of aqueous geochemistry developed at the Lawrence Livermore National Labs in ???. 

While EQ3/6 reliably handles a very large number of equilibrium geochemical calculations and problems, 

EQ3/6 calculates what would happen in natural water-based system, if equilibrium is reached. This requires partitioning of the elements in a water-based system into solution (speciation), and coexisting solid phases. Eleanor expands on this capability, by parallelizing execution of individual systems across ranges of input parameters. These ranges can either explore natural progression of a variable in time, or reflect uncertainty in a variable mimicking its uncertainty in the environment.

Eleanor is designed with specific problem types in mind. For example:
What are all fluid compositions that are consistent with the equilibrium presence of specific solids (minerals) and/or gasses (atmospheres). `Eleanor` therefore allows practitioners to estimate the uncertainty inherent in geochemical systems by 

Eleanor than therefor generate very large geochemical datasets that inform that list all possible system speciations that are possible, given the uncertainty outlined in the input constraints.

# Background

# Statement of Need

Clearly illustrates the research purpose of the software and places it in the context of related work.

Eleanor automates the execution of the speciation software EQ3/6, such that all possible fluid compositions (within some resolution), consistent with the presence of either a mineral or a gas (ie, part of a rock, or an atmosphere), can be determined.. 
Existing Software

Many open source and proprietary software packages currently exist for speciating aqueous solutions (see Wolery and Jove Colon, 2018, and sources therein). These packages, like EQ3/6, require bulk compositional constraints (such as a well defined rock composition and water composition), state variable constraints (temperature and pressure), and thermodynamic data for some set of dissolved, gaseous, and solids species, and return to the user the system that would form if the 

Many mathematical techniques exist for calculating the anticipated behavior of aqueous chemical systems. Codes that automate these techniques (both open source and those behind paywalls) fall very loosely into three categories: 
(1) Codes that calculate the thermodynamic properties of chemical species, and their relationship to one another. These include SUPCRT (Johnson et al., 1992), CHNOSZ (Dick, 2008; 2019; 2021), THermoFun (https://github.com/thermohub/thermofun)
codes that additionally partition elemental mass into different phases and dissolved chemical species based on these thermodynamic properties, and codes that additionally place these phases and species in a spatial and temporal landscape designed to mimic natural systems (reactive transport modeling)

Existing chemical thermodynamic tools can be roughly divided into three categories: Those that calculate equilibrium properties properties of natural systems 
Some codes spealizie in calcualtiong equilibrium properties from standarized databases (SUPCRT, CHNOSZ, Thermofun). Do less: 

Supcrt: (point calculations)
CHNOSZ:(talk to grayson)
ThermoFun: https://github.com/thermohub/thermofun i think this is a supcrt-type tool

MINEQL: for purchase (https://mineql.com/)
PHREEQE family: (https://www.usgs.gov/software/phreeqc-version-3)
SOLVEQ:

Additionally, platforms employing a combination of these tools and additional custom problem-specific tools exist. THese include ENKI, WORM, ThermoEcos (https://thermohub.org/), to name a few

Do more: reactive transport modeling.
Thoughreact: https://tough.lbl.gov/software/toughreact_v4-13-omp/

Past and Ongoing research using Eleanor and her beta predecessors.

Ocean worlds Magnetite project (cite AbSciCon abstract)

Py Synthesis work (cite Brandys goldschmidt abstract)

# Features and API

# Example Usage - Seasonality of Calcite Dissolution at the Bermudian Seafloor

# Team Members

39 Alpha Research organizes teams of researches who publish under a team name rather than individually. Members of the Team 0 team along with a research profile for the team as a whole can be found at https://39alpharesearch.org/about/teams/t0/.

# Acknowledgements

# References

Must include other software addressing similar needs. No abbreviations.

Cite NASA NPP grant and OW main grant (given UM paper)

Cite my thesis

Cite Mars work with Tom

Cite UM work
