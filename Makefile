.PHONY:	clean dist upload

all: dist

dist:
	python setup.py sdist

upload:
	twine upload dist/*

clean:
	rm -rf build dist foo.db zamia_prolog.egg-info

