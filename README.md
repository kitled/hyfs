# HyFS
> A **Hy**per **F**ile**S**ystem

HyFS (`hyfs`) is a meta-filesystem, designed to logically handle entities (files, directories) across a variety of actual filesystems and storage units.

The first implementation relies on `xattr` so remains confined to the POSIX-compliant world of UNIX/Linux.

It's primarily meant as a human-friendly kind of file storage wrapper, where you can rename and move things around without breaking the semantic (meaning) or structural (logic) relationships you've established between things. It's meant to allow multiple kinds of views and organizations to fit with your current mental angle at all times, non-destructively to the underlying 'hard' linear structure.
