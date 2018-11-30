
test: clean-test
	python write_meta.py -v test/resources/

test-dry: clean-test
	python write_meta.py -v -d test/resources/

clean-test:
	rm -rf tests/resources_test* && cp -R tests/resources tests/resources_test