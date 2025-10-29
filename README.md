# HyFS
> A **Hy**per **F**ile**S**ystem

> [!WARNING]
> The very name of this project is still in flux.  
> 
> It went from `fsxp` (filesystem explorer) to `hyfs` (hyper filesystem) already.  
> 
> I'm considering calling it something like `hyes` (hyper entity system).  
> "Entity", or any word meaning the idea of some element, is really what this is. Not some "file" system, even though it's evidently based on files. But its future evolution will transcend this boundary. Both within (extracting and considering pieces of files, notably using custom 'magics'), and without (distributing & merging stuff around).
> 
> As I explore the design of this project, it becomes into its own thing. The name will be the result of reaching some v1.0 MVP, not something I can pre-plan.

HyFS (`hyfs`) is a meta-filesystem, designed to logically handle entities (files, directories) across a variety of actual filesystems and storage units.

The first implementation relies on `xattr` so remains confined to the POSIX-compliant world of UNIX/Linux.

It's primarily meant as a human-friendly kind of file storage wrapper, where you can rename and move things around without breaking the semantic (meaning) or structural (logic) relationships you've established between things. It's meant to allow multiple kinds of views and organizations to fit with your current mental angle at all times, non-destructively to the underlying 'hard' linear structure.
