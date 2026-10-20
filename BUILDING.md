How this repository is structured
------------------------
Because we need to constantly rebase on top of Valve's Proton, this repository
is not using the typical branching strategy of having a `master` or `main` 
as the default branch that holds the most recent development version. Instead
the default branch is `cachyos_main` which holds the documentation.

The code resides in versioned branches named after their respective releases.
These branches follow the pattern of
```
cachyos_<majorver>_<date>/<subpath>
```

### `<majorver>_<date>`
Depends on the version used as the basis of each release, and usually it is
inherited from Proton's `experimental-<majorver>-<date>` tags from the
respective `experimental_<majorver>` branch.

### `<subpath>`
The subpaths `main` and `main_native` hold the final releases for the
Steam Linux Runtime and host-native builds respectively. For the most recent
release, or the one being worked one, other subpaths might exist such as
`_sauce`, `_umu`, `_action` and `_native`. These branches starting with an
underscore are usually collections of commits for a specific set of features,
which are later merged into the `main` and `main_native` subpaths to construct
the final source tree for that release.


Obtaining Proton-CachyOS sources
------------------------

Acquire Proton's source by cloning <https://github.com/CachyOS/proton-cachyos>
and checking out the branch you desire.

You can clone the latest Proton to your system with this command:

```bash
git clone --branch cachyos_11.0_20260506/main --tags https://github.com/CachyOS/proton-cachyos proton-cachyos
```

Be sure to update submodules when switching between branches:

```bash
git checkout cachyos_11.0_20260506/main
git submodule update --init --recursive [--filter=tree:0]
```

`--filter=tree:0` is optional and it will create a "swallow" clone but retains
full version information, which is important for building, and the ability to
traverse the repository's history. Use if you only want to build Proton, for
development purposes it is strongly suggested to avoid it.

If you want to change any subcomponent, now is the time to do so. For
example, if you wish to make changes to Wine, you would apply them to the
`wine/` directory.


Applying custom patches
------------------------
For the major components, patches and modification are normally applied in their
respective repositories, and their submodules are updated accordingly. For example,
Wine's source is included from [wine-cachyos][wine-cachyos].

For minor components, or components that a fork doesn't exist because the modification
are temporary, the `patches` folder is used. Each submodule has its own patches folder,
as such patches for `protonfixes` go into `patches/protonfixes`. Patches for `wine`
can also be applied this way, but it's not preferable other than testing.

The order they are applied depends on their lexicographical ordering. For example,
for wine you can place them into `patches/wine` and the build system will pick them
up and apply them. Patches can also be in subfolders, with `patches/wine/0001-<something>`
folder applied before `patches/wine/0002-<else>`.

Not all components have support for kind of patching, it is added per-case when it's required.
You can find out which components already support this by using
```bash
grep -E 'post-source:.*patches-source' Makefile.in
```

If you need to add ephemeral patches in some component which doesn't already have this option,
you can use the following from `glslang` as a template.
```makefile
$(OBJ)/.glslang-post-source: patches-source
	$(foreach p,$(shell find $(PATCHES_SRC)/glslang/ -name "*.patch" | sort),patch -d $(GLSLANG_SRC) -Np1 -i $(p) &&) true
	touch $@
```

[wine-cachyos]: https://github.com/CachyOS/wine-cachyos


Building Proton
---------------

Most of Proton builds inside the Proton SDK container with very few
dependencies on the host side.

## Preparing the build environment

You need either a Docker or a Podman setup which Proton's build system uses
internally. You should never need to use either container engine manually unless
working on those parts of build system directly.

We highly recommend [the rootless Podman setup][rootless-podman]. Please refer
to your distribution's documentation for setup instructions (e.g. Arch
[Podman][arch-podman] / [Docker][arch-docker], Debian [Podman][debian-podman] /
[Docker][debian-docker]).

[rootless-podman]: https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md
[arch-podman]: https://wiki.archlinux.org/title/Podman
[arch-docker]: https://wiki.archlinux.org/title/Docker
[debian-podman]: https://wiki.debian.org/Podman
[debian-docker]: https://wiki.debian.org/Docker


## The Easy Way (unsupported)

We provide a top-level Makefile which will execute most of the build commands
for you.

After checking out the repository and updating its submodules, assuming that
you have a working Docker or Podman setup, you can build and install Proton
with a simple:

```bash
make install
```

If your build system is missing dependencies, it will fail quickly with a clear
error message.

After the build finishes, you may need to restart the Steam client to see the
new Proton tool. The tool's name in the Steam client will be based on the
currently checked out branch of Proton. You can override this name using the
`build_name` variable.

See `make help` for other build targets and options.



## Manual building

### Configuring the build

```bash
mkdir ../build && cd ../build
../proton-cachyos/configure.sh --enable-ccache --build-name=my_build
```

Running `configure.sh` will create a `Makefile` allowing you to build Proton.
The scripts checks if containers are functional and prompt you if any
host-side dependencies are missing. You should run the command from a
directory created specifically for your build.

The configuration script tries to discover a working Docker or Podman setup
to use, but you can force a compatible engine with
`--container-engine=<executable_name>`.

You can enable ccache with `--enable-cache` flag. This will mount your
`$CCACHE_DIR` or `$HOME/.ccache` inside the container.

`--proton-sdk-image=registry.gitlab.steamos.cloud/proton/soldier/sdk:<version>`
can be used to build with a custom version of the Proton SDK images.

Check `--help` for other configuration options.

NOTE: If **SELinux** is in use, the Proton build container may fail to access
your user's files. This is caused by [SELinux's filesystem
labels][selinux-labels]. You may pass the `--relabel-volumes` switch to
configure to cause the [container engine to relabel its
bind-mounts][bind-mounts] and allow access to those files from within the
container. This can be dangerous when used with system directories. Proceed
with caution and refer your container engine's manual.

[selinux-labels]: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/security-enhanced_linux/sect-security-enhanced_linux-working_with_selinux-selinux_contexts_labeling_files
[bind-mounts]: https://docs.docker.com/storage/bind-mounts/


### Building

```
make
```

**Important make targets:**

`make install` - install Proton into your user's Steam directory, see the [install Proton
locally](#install-proton-locally) section for details.

`make redist` - create a redistribute build (`redist/`) that can be copied to
`~/.steam/root/compatibilitytools.d/`.

`make deploy` - create a deployment build (`deploy/`). This is what we use to
deploy Proton to Steam users via Steamworks.

`make module=<module> module` - build both 32- and 64-bit versions of the
specified wine module. This allows rapid iteration on one module. This target
is only useful after building Proton.

`make dxvk` / `make vkd3d-proton` - rebuild DXVK / vkd3d-proton.


### Figuring Out What Failed To Build

Proton build system invokes builds of many subprojects in parallel. If one
subprojects fails there can be thousands of lines printed by other sub-builds
before the top level exits. This can make the real reason of the build failing
hard to find.

Appending `2>&1 | tee build.log` will log the full build output to a `build.log`
file. Searching that file from the bottom up for occurrences of `Error` should
point to the right area. E.g.:

```
make 2>&1 | tee build.log
grep -n '] Error [0-9]' build.log
```

```
11220:make: *** [../Makefile.in:465: /builds/proton/proton/build-dir/.kaldi-i386-configure] Error 1
12427:make: *** [../Makefile.in:1323: deploy] Error 2
```


### Debug Builds

To prevent symbol stripping add `UNSTRIPPED_BUILD=1` to the `make`
invocation. This should be used only with a clean build directory.

E.g.:

```
mkdir ../debug-proton-build && cd ../debug-proton-build
../proton/configure.sh --enable-ccache --build-name=debug_build
make UNSTRIPPED_BUILD=1 install
```


### ARM64 Builds

You need an ARM64 build machine and pass `--target-arch=arm64` to `configure.sh`.

It's not possible to use the resulting builds in x86 Steam running via FEX.


Install Proton locally
----------------------

Steam ships with several versions of Proton, which games will use by default or
that you can select in Steam Settings' Steam Play page. Steam also supports
running games with local builds of Proton, which you can install on your
machine.

To install a local build of Proton into Steam, make a new directory in
`~/.steam/root/compatibilitytools.d/` with a tool name of your choosing and
place the directory containing your redistributable build under that path.

The `make install` target will perform this task for you, installing the
Proton build into the Steam folder for the current user. You will have to
restart the Steam client for it to pick up on a new tool.

A correct local tool installation should look similar to this:

```
compatibilitytools.d/my_proton/
├── compatibilitytool.vdf
├── filelock.py
├── LICENSE
├── proton
├── proton_dist.tar
├── toolmanifest.vdf
├── user_settings.sample.py
└── version
```

To enable your local build in Steam, go to the Steam Play section of the
Settings window. If the build was correctly installed, you should see
"proton-localbuild" in the drop-down list of compatibility tools.

Each component of this software is used under the terms of their licenses.
See the `LICENSE` files here, as well as the `LICENSE`, `COPYING`, etc files
in each submodule and directory for details. If you distribute a built
version of Proton to other users, you must adhere to the terms of these
licenses.


Debugging
---------

Proton builds have their symbols stripped by default. You can switch to
"debug" beta branch in Steam (search for Proton in your library,
Properties... -> BETAS -> select "debug") or build without stripping (see
[Debug Builds section](#debug-builds)).

The symbols are provided through the accompanying `.debug` files which may
need to be explicitly loaded by the debugging tools. For GDB there's a helper
script `wine/tools/gdbinit.py` (source it) that provides `load-symbol-files`
(or `lsf` for short) command which loads the symbols for all the mapped files.

For tips on debugging see [docs/DEBUGGING-LINUX.md](docs/DEBUGGING-LINUX.md)
and [docs/DEBUGGING-WINDOWS.md](docs/DEBUGGING-WINDOWS.md).


`compile_commands.json`
-----------------------

For use with [clangd](https://clangd.llvm.org/) LSP server and similar tooling.

Projects built using cmake or meson (e.g. vkd3d-proton) automatically come with
`compile_commands.json`. Wine also generates the file on its own via `makedep`.

Proton's build system collects all the `compile_commands.json` files in a build
subdirectory named `compile_commands/`.

The paths are translated to point to the real source (i.e. not the rsynced
copy). It still may depend on build directory for things like auto-generated
`config.h` though and for wine it may be beneficial to run `tools/make_requests`
in you source directories as those changes are not committed.

You can then configure your editor to use that file for clangd in a few ways:

1) directly - some editors/plugins allow you to specify the path to `compile_commands.json`
2) via `.clangd` file, e.g.
```bash
cd src/proton/wine/
cat > .clangd <<EOF
CompileFlags:
  CompilationDatabase: ../build/current-dev/compile_commands/wine-x86_64/
EOF
```
3) by symlinking:
```bash
ln -s ../build/current-dev/compile_commands/wine-x86_64/compile_commands.json .
```

<!-- Target:  GitHub Flavor Markdown.  To test locally:  pandoc -f markdown_github -t html README.md  -->
