# Bulker registry

Welcome to the bulker registry. Here, he host manifest files that describe computing environments for use with the [bulker environment manager](http://bulker.io). The bulker registry is hosted on github pages, which provides a manifests to test with bulker. If you want to contribute a manifest, feel free to issue a pull request. In the future, we envision the bulker registry as a full-featured RESTful API to share bulker environments. 

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
