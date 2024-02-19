# Contributing

- [Documentation](#documentation)
- [Development](#development)
  * [Commits](#commits)
  * [Pull requests](#pull-requests)

First of all, thank you for taking the time to help this project, it means a lot.

To sum-up:
* You know how to Python? You can help the project by [reviewing code](https://github.com/AMustache/Gratte-Papier/pulls), [fixing bugs](https://github.com/AMustache/Gratte-Papier/issues), and [adding features](https://github.com/AMustache/Gratte-Papier/issues)!
* You know how to data analysis? You can help the project by [providing insights about data sources](https://github.com/AMustache/Gratte-Papier/wiki)!
* No matter what you know, you can always report a bug or [ask for a feature](https://github.com/AMustache/Gratte-Papier/issues), [discuss about the project](https://github.com/AMustache/Gratte-Papier/discussions), or [get in touch](mailto:stache@stache.cat)!

## Documentation

Documentation is particularly important for us, and for this project in particular. Thus, any help is welcome, let alone fixing typos.

- In general, you should not hesitate to be clear about "how it works"!
- This means documenting when you add something, documenting when you change something, documenting when you test something, ...
- In short, documenting so that the next person has to look for it as little as possible!

## Development

Before anything, make sure you followed the [quickstart](./README.md#Setup).

### Commits

Regarding commit messages:
- [Don't do that](https://xkcd.com/1296/), and we're cool.
- When fixing an issue, please explicit it using the "Fix" keyword, and the exact title of the issue. (e.g., "Fix #42: Loader does not load").

### Pull requests

We follow the [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow): all code contributions are submitted via a pull request towards the main branch.

1. Fork the project or open a new branch.
2. Manually bump the version in `setup.py`.
  - Major if your changes are breaking.
  - Minor if your changes are not breaking.
  - Patch is made on a per-commit basis.
3. Complete your modifications.
4. Merge the master branch.
5. Open a PR.

Moreover:
- When creating a new branch to fix an issue, please refer to the issue in the branch name, starting by its number (e.g., `42-loader-does-not-load`).
- The title of your PR must be explicit.
- When fixing an issue, please explicit it using the "Fix" keyword, and the exact title of the issue. (e.g., "Fix #42: Loader does not load").
- The description may contain any additional information (the more the merrier!), but do not forget to mirror it in the documentation when needed.
- Please take into account that your PR will result in one commit; you may want to squash/rebase yourself beforehand.
- Please link the issues and the PR when needed.
