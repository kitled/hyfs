# HyFS
> A **Hy**per **F**ile**S**ystem

> [!WARNING]
> The very name of this project is still in flux.  
> 
> It went from `fsxp` (filesystem explorer) to `hyfs` (hyper filesystem) already.  
> 
> I'm considering calling it something like `hyes` (hyper entity system).  
> "Entity", or any word meaning the idea of some element, is really what this is. Not some "file" system, even though it's evidently based on files. But its future evolution will transcend this boundary. Both within (extracting and considering pieces of files, notably using custom 'magics'), and without (distributing & merging stuff around).  
> But this is most likely not the final name, either.
> 
> As I explore the design of this project, it becomes its own thing. The name will be the result of reaching some v1.0 MVP, not something I can predict (because that's what it would be, since I'm using an exploratory approach whose destination is unknown even to me).

----

(tentative README)

## Intro

HyFS (`hyfs`) is a meta-filesystem, designed to logically handle entities (files, directories) across a variety of actual filesystems and storage units.

The first implementation relies on `xattr` so remains confined to the POSIX-compliant world of UNIX/Linux.

It's primarily meant as a human-friendly kind of file storage wrapper, where you can rename and move things around without breaking the semantic (meaning) or structural (logic) relationships you've established between things. It's meant to allow multiple kinds of views and organizations to fit with your current mental angle at all times, non-destructively to the underlying 'hard' linear structure.

## Goals
> Visions of where this is going

Things you should be able to do with a complete version of the code:


- Elements / Entities are not tied to a specific type of object
    - You can manipulate bits of text, parts of files, files themselves, directories, remote resources (SSH, fetch, HTTP API, whatever), arbitrary mixes of any "type", with the same tools and interfaces. It is agnostic in the same way you can grab a piece of paper, a notebook, and a mail in the same hand and use them side by side regardless of those objects "type".
    - Compose "views" made of arbitrary entities (files, groups thereof, parts thereof). E.g this lets you insert your own bits and parts of notes in new and original ad hoc ways to suit your exact need at all times.

- Unified memory space
    - Different places, same space: inspect your entire memory space as if all entities were in the same place
    - 
    - Feels local, snappy (use dict indexes etc.)
    - 






