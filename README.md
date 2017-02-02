# optitrack-driver

This repository contains a python application which translates data
streamed from the Optitrack Motive software (aka NatNet) into LCM
messages.

To build:

```bazel build //...```

To run:

```bazel run //src:optitrack_client```

## TODO items

 * Figure out how to correctly export the built LCM types
 * Parameterize the server IP address (and probably the multicast address)
 * Poll for data definitions (marker sets, rigid bodies, etc) from
   Motive and republish.
