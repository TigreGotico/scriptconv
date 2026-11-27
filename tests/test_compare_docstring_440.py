"""The compare command example asks for a sentence set the caller supplies."""
import scriptconv.testing.compare as compare


def test_the_example_does_not_name_a_file_that_the_repository_lacks():
    doc = compare.__doc__
    assert "tests/data/sentences/pt-PT.tsv" not in doc
    assert "--tsv /path/to/sentences.tsv" in doc
    assert "Build a TSV with the header above" in doc
