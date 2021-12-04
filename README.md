# Eleanor

A package for large scale aqueous geochemical modelling. 


## Install 

Aspirationally we want the install to be as simple as 

```pip install elanor```

We'll see if that's a reality. 


## A warning 

The goal of this code is to make running geochemical models at scale easier. Running those models
and getting an answer without an error does not mean you've set up a physically meaningful model.
This software is not a substitute for a principled understanding of the underlying chemistry. 
While we hope other scientists can use this software to help answer questions about their system of
interest, we also recognize that there are likely more ways to use this software incorrectly than 
correctly. We aim to protect against these cases but that attempt will always be incomplete. 

All of this is to say - we hope this project helps you do science faster. But faster doesn't 
mean correct. 

## Dependencies 

### EQ3/6
The easist way to understand what Eleanor is doing is to understand that its helping you run 
geochemical simulations by calling `EQ3/6`. Naturally that means `EQ3/6` is a required 
dependency. The original code is hosted by 
[Lawerence Livermore National Lab](https://www-gs.llnl.gov/energy-homeland-security/geochemistry)
but we have made a version we host on 
[github](https://github.com/39alpha/eq3_6), which we recommend. The only 
differences between the code distributed by LLNL and the code we've put on git is in the way 
input/output data is processed. We used continuous integration to ensure the "geochemistry" hasn't 
been affected by our changes. See the docs on [github](https://github.com/39alpha/eq3_6) for more 
information. 

### Other Python dependencies 
NA 

## data0 files 

Description of data0 files, where they come from, what they mean, and how they change the outcomes

## Documentation 

Information and link to complete documentation

## Contributing the Eleanor

Some suggestions 