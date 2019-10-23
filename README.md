# Bulker registry

Welcome to the bulker registry. Here, we host manifest files that describe computing environments for the [bulker environment manager](http://bulker.io). The bulker registry is hosted on github pages. In the future, we envision the bulker registry as a full-featured RESTful API to share bulker environments. 

## Linking your bulker CLI to hub.bulker.io

 You can link your bulker CLI to this registry by adding this line to your bulker config file:

```yaml
registry_url: https://hub.bulker.io
```

Or, equivalently, you can also link directly like this:

```yaml
registry_url: https://raw.githubusercontent.com/databio/hub.bulker.io/master/
```

## Contributing a manifest

### Write a manifest 

First, you have to write a manifest yaml file. Consult the [bulker docs on how to write a manifest](http://docs.bulker.io/en/latest/manifest/).

### Upload your manifest to the registry

After creating your manifest file, you can contribute it to this registry so that you and others can more easily load it with the bulker CLI.  Name your manifest yaml file with the name of the manifest. For a tag, append an understore, so it's `manifestname_tag.yaml`. Manifests in the registry are divided into namespaces, which are represented as subfolders in this repository. So, place your manifest into an appropriate subfolder, and then open a pull request.

Once merged, you will be able to pull your manifest with `bulker load namespace/manifestname:tag`.


