# Bulker registry

Welcome to the bulker registry. We're currently hosting the bulker registry on github pages. At the moment, this is a barebones server that provides a few in-house manifests for you to test with bulker. In the future, we envision this as a full-featured RESTful API with a user interface to allow you to identify and download existing manifests, as well as share your own environments with others. 

## Linking to hub.bulker.io

 You can link your bulker CLI to this registry by adding this line to your bulker config file:

```yaml
registry_url: https://hub.bulker.io
```

Or, equivalently, you can also link directly like this:

```yaml
registry_url: https://raw.githubusercontent.com/databio/hub.bulker.io/master/
```

## Organization

Manifests are divided into namespaces. Each subfolder in this repository is a namespace. The filename of the yaml file is the name of the manifest. For a tag, append an understore, so it's `namespace/manifestname_tag.yaml`.

You can then pull this manifest with `bulker load namespace/manifestname:tag`.


## Contributing

Submit your own manifests in your own namespace via PR.
