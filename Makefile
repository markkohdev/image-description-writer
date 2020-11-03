
test: clean-test
	python write_meta.py -v test/renamer/resources_test/

test-dry: clean-test
	python write_meta.py -v -d test/renamer/resources_test/

# Re-copy the test resources into the resources_test dir (where we run the tests on)
clean-test:
	rm -rf tests/renamer/resources_test* && cp -R tests/renamer/resources tests/renamer/resources_test