# Contributing to Eleanor

Thanks for taking the time to make Eleanor better!

#### Table of Contents

[Code of Conduct](#code-of-conduct)

[How can I contribute?](#how-can-i-contribute)
  * [Reporting Bugs](#reporting-bugs)
  * [Suggesting Features](#suggesting-features)
  * [Your First Code Contribution](#your-first-code-contribution)
  * [Pull Requests](#pull-requests)

[Style Guides](#style-guides)
  * [Git Commit Messages](#git-commit-messages)
  * [Python Style Guide](#python-style-guide)
  * [Documentation Style Guide](#documentation-style-guide)

[Additional Notes](#additional-notes)

## Code of Conduct

This project, and everyone participating in it, is governed by the [Eleanor Code of
Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report
unacceptable behavior to [39alpha@39alpharesearch.org](mailto:39alpha@39alpharesearch.org).

## How can I contribute?

### Reporting Bugs

This section guides you through submitting a bug report for Eleanor. Following these guidelines
helps maintainers and the community understand your report, reproduce the behavior, and find related
reports.

Before creating bug reports, perform a [cursory
search](https://github.com/39alpha/eleanor/issues) to see if the problem has already been reported.
If it has **and the issue is still open**, add a comment to the existing issue instead of opening a
new one. If you find a **closed** issue that seems like it is the same thing that you're
experiencing, open a new issue and include a link to the original issue in the body of your new one.

#### How do I submit a bug report?

Bugs are tracked as [GitHub issues](https://guides.github.com/features/issues/). After you are sure
the bug is either new, or needs to be readdressed, create an issue on the [Eleanor issue
tracker](https://github.com/39alpha/eleanor/issues) and provide the following information:

Explain the problem and include additional details to help maintainers reproduce the problem:

  * **Use a clear and descriptive title** for the issue to identify the problem.
  * **Describe the exact steps which reproduce the problem** in as many details as possible. For
    example, include a minimal script or order file to reproduce the bug.
  * **Describe the behavior you observed** and point out exactly what the problem is with that
    behavior. For example, include any output you observe and explain what is wrong with it.
  * **Explain what behavior you expected to see instead and why.**

Provide more context by answering these questions:

  * **Did the problem start happening recently** (e.g. after updating to a new version of Eleanor)
    or was this always a problem?
  * If this problem started recently, **can you reproduce the problem in an older version of
    Eleanor?** What is the most recent version of Eleanor which does not have this bug?
  * **Can you reliably reproduce the issue?** If not, provide details about how often the problem
    happens and under which conditions it typically occurs.
  * If the problem is related to working with external resources (e.g. data files, network
    connections, a PostgreSQL database, etc...), **does the problem happen for all resources, or
    only some?**

Include details about your configuration:

  * **Which version of Eleanor are you using?**
  * **What's the name and version of the Operating System you are using?**

### Suggesting Features

This section guides you through submitting a feature suggestion for Eleanor, including completely
new features and minor improvements to existing functionality. Following these guidelines helps
maintainers and the community understand your suggestion, find related suggestions, and prioritize
feature development.

Before creating a feature request, perform a [cursory
search](https://github.com/39alpha/eleanor/issues?q=is%3Aissue+label%3A%22feature+request%22) to
see if it has already been suggested. If it has, add a comment to the existing issue instead of
opening a new one.

#### How do I submit a feature request?

Feature requests are tracked as [GitHub issues](https://guides.github.com/features/issues/). After
you are sure the request is not a duplicate, create an issue on the [Eleanor issue
tracker](https://github.com/39alpha/eleanor/issues).

  * **Use a clear and descriptive title** for the issue to identify the suggestion.
  * **Provide a description of the feature** in as much detail as possible.
  * **Propose a configuration schema or plugin interface** to demonstrate how the feature fits in
    with the rest of Eleanor. For example, show how it would be expressed in a config or order file,
    or sketch a plugin entry-point implementation.
  * **Give an example usage** for the proposed feature.
  * **Reference any resources** on which the feature is based. Include any mathematical or
    scientific details necessary for implementing the feature, e.g. relevant equations or citations.

### Your First Code Contribution

Your contributions are more than welcome! It's also advisable that you read through the
[documentation](https://39alpha.github.io/eleanor) to make sure that you fully understand how the
various components of Eleanor interact before you get started.

For external contributions, we use [GitHub forks](https://guides.github.com/activities/forking/)
and [pull requests](https://guides.github.com/activities/forking/#making-a-pull-request) workflow.
To get started with contributing code, you first need to fork Eleanor to one of your accounts. As
you begin development, we have several recommendations that will make your life easier.

 * **Do not work directly on main.** Create a branch for whatever feature or bug you are currently
   working on.
 * **Create a [draft pull
   request](https://github.blog/2019-02-14-introducing-draft-pull-requests/)** after you first push
   to your fork. This will ensure that the rest of the Eleanor community knows that you are working
   on a given feature or bug.
 * **Fetch changes from [39alpha/eleanor](https://github.com/39alpha/eleanor)'s main branch
   often** and merge them into your working branch. This will reduce the number and severity of
   merge conflicts that you will have to deal with. [How do I fetch changes from
   39alpha/eleanor?](#how-do-i-fetch-changes-from-39alphaeleanor)

### Pull Requests

The Fork-Pull Request process described here has several goals:

  * Maintain Eleanor's quality
  * Quickly fix problems with Eleanor that are important to users
  * Engage the community in working to make Eleanor as near to perfect as possible
  * Enable a sustainable system for Eleanor's maintainers to review contributions

Please follow these steps to have your contribution considered by the maintainers:

  1. **Use a clear and descriptive title** for your pull request.
  2. Follow the [styleguides](#style-guides).
  3. After you submit your pull request, verify that all
     [status checks](https://help.github.com/articles/about-status-checks/) are passing.
     <details>
       <summary>What if the status checks are failing?</summary>
       If a status check is failing, it is your responsibility to fix any problems. Of course the
       maintainers are here to help, so please post a comment on the pull request if you need any
       support from us. If you believe that the failure is unrelated to your change, please leave a
       comment on the pull request explaining why you believe that to be the case. A maintainer will
       re-run the status checks for you. If we conclude that the failure was a false positive, then
       we will open an issue to track that problem with our own status check suite.
     </details>

## Style Guides

### Git Commit Messages

* Use the present tense ("Add csv output sink" not "Added csv output sink")
* Use the imperative mood ("Fix navigator batch size..." not "Fixes navigator batch size...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line
* When only changing documentation, include `[skip-ci]` in the commit title
* Consider starting the commit message with an applicable emoji:
    - :art: `:art:` when improving the format/structure of the code
    - :racehorse: `:racehorse:` when improving performance
    - :book: `:book:` when writing documentation
    - :penguin: `:penguin:` when fixing something on Linux
    - :apple: `:apple:` when fixing something on macOS
    - :checkered_flag: `:checkered_flag:` when fixing something on Windows
    - :bug: `:bug:` when fixing a bug
    - :hammer: `:hammer:` when adding code or files
    - :fire: `:fire:` when removing code or files
    - :green_heart: `:green_heart:` when fixing the CI build
    - :heavy_check_mark: `:heavy_check_mark:` when adding or modifying tests
    - :arrow_up: `:arrow_up:` when upgrading dependencies
    - :arrow_down: `:arrow_down:` when downgrading dependencies
    - :shirt: `:shirt:` when dealing with linter warnings

### Python Style Guide

All Python code must adhere to the [PEP 8 Style Guide for Python
Code](https://www.python.org/dev/peps/pep-0008/), with a maximum line length of 120 characters.

To enforce this, we use [ruff](https://docs.astral.sh/ruff/). We recommend running it **before**
each commit (the pre-commit hooks will do this automatically if you have them installed). To run
manually:

```shell
$ ruff check --fix eleanor
$ ruff format eleanor
```

Type annotations are required for all public functions and methods. We use
[basedpyright](https://github.com/DetachHead/basedpyright) for static type checking:

```shell
$ basedpyright eleanor
```

### Documentation Style Guide

#### Website Documentation

The Eleanor website lives in the [`docs/`](docs/) directory and is built with
[Quarto](https://quarto.org/). Documentation pages are written in
[Markdown](https://quarto.org/docs/authoring/markdown-basics.html) (`.qmd` files).

* Use Markdown for all prose
* Use fenced code blocks with language identifiers for all code examples
* Be liberal with examples — show realistic Eleanor workflows where possible
* Use math fences (`` ```{math} ``) or inline `$...$` for equations where applicable

#### Code Documentation

Each module, class, function, and method should be documented using a Python docstring. Use plain
prose docstrings; detailed parameter/return type information is conveyed via type annotations.

* Be very **liberal** with examples in docstrings
* Use `::` followed by an indented block for inline code examples

##### Modules

All modules should have a short docstring describing their purpose and the public names they export.

##### Classes

All classes should have a docstring describing the class, its responsibilities, and — where helpful
— example construction and usage:

```python
class MyNavigator(AbstractNavigator):
    """A navigator that samples points uniformly at random.

    Useful for exploratory runs over a large variable space. On each call
    to :meth:`navigate` it draws *batch_size* independent samples::

        nav = MyNavigator(seed=42)
        points = list(nav.navigate(space, batch_size=100))
    """
```

##### Functions and Methods

All public functions and methods should have a docstring that includes a brief description and, when
the behavior is non-obvious, an example:

```python
def navigate(self, space: VariableSpace, *, batch_size: int) -> Generator[Point, None, None]:
    """Yield *batch_size* points sampled uniformly from *space*::

        for point in navigator.navigate(space, batch_size=50):
            results = kernel.run(point)
    """
```

## Additional Notes

### How do I fetch changes from 39alpha/eleanor?

After you have cloned your fork, add [39alpha/eleanor](https://github.com/39alpha/eleanor) as a
remote:
```shell
$ git remote add upstream https://github.com/39alpha/eleanor
```
To fetch changes from Eleanor's main branch:
```shell
$ git fetch upstream main
```
This will get all of the changes from the main repository's main branch, but it will not merge any
of those changes into your local working branches. To do that, use `merge`:
```shell
$ git checkout main
$ git merge upstream/main
...
```
You can then merge the changes into your feature branch (say `my-feature`)
```shell
$ git checkout my-feature
$ git merge main
```
and then deal with any merge conflicts as usual.
