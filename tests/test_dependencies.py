def test_tensorflow_hub_imports_in_clean_environment():
    import tensorflow_hub
    assert tensorflow_hub.__version__ == "0.16.1"

