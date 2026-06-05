import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useListUsers,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  getListUsersQueryKey,
  type User,
} from "@workspace/api-client-react";
import { UserPlus, Trash2, Pencil, ShieldCheck, User as UserIcon, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/hooks/use-auth";

function errorMessage(err: unknown, fallback: string): string {
  const data = (err as { data?: unknown })?.data;
  const detail = (data as { detail?: string })?.detail;
  return detail || fallback;
}

export default function Users() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user: currentUser } = useAuth();
  const { data: users, isLoading } = useListUsers();

  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [deleteUser, setDeleteUser] = useState<User | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() });

  // ---- Create ----
  const [cUsername, setCUsername] = useState("");
  const [cPassword, setCPassword] = useState("");
  const [cFullName, setCFullName] = useState("");
  const [cEmail, setCEmail] = useState("");
  const [cRole, setCRole] = useState("operator");

  const resetCreate = () => {
    setCUsername("");
    setCPassword("");
    setCFullName("");
    setCEmail("");
    setCRole("operator");
  };

  const createUser = useCreateUser({
    mutation: {
      onSuccess: () => {
        invalidate();
        setCreateOpen(false);
        resetCreate();
        toast({ title: "User created" });
      },
      onError: (e) =>
        toast({
          title: "Could not create user",
          description: errorMessage(e, "Please try again."),
          variant: "destructive",
        }),
    },
  });

  // ---- Edit ----
  const [eFullName, setEFullName] = useState("");
  const [eEmail, setEEmail] = useState("");
  const [eRole, setERole] = useState("operator");
  const [eActive, setEActive] = useState(true);
  const [ePassword, setEPassword] = useState("");

  const openEdit = (u: User) => {
    setEditUser(u);
    setEFullName(u.full_name ?? "");
    setEEmail(u.email ?? "");
    setERole(u.role);
    setEActive(u.is_active);
    setEPassword("");
  };

  const updateUser = useUpdateUser({
    mutation: {
      onSuccess: () => {
        invalidate();
        setEditUser(null);
        toast({ title: "User updated" });
      },
      onError: (e) =>
        toast({
          title: "Could not update user",
          description: errorMessage(e, "Please try again."),
          variant: "destructive",
        }),
    },
  });

  // ---- Delete ----
  const deleteUserMut = useDeleteUser({
    mutation: {
      onSuccess: () => {
        invalidate();
        setDeleteUser(null);
        toast({ title: "User deleted" });
      },
      onError: (e) =>
        toast({
          title: "Could not delete user",
          description: errorMessage(e, "Please try again."),
          variant: "destructive",
        }),
    },
  });

  return (
    <div className="container max-w-5xl px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Manage who can access the monitoring wall and what they can do.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add User
        </Button>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                </TableCell>
              </TableRow>
            )}
            {users?.map((u) => (
              <TableRow key={u.id}>
                <TableCell>
                  <div className="font-medium">
                    {u.username}
                    {currentUser?.id === u.id && (
                      <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                    )}
                  </div>
                  {(u.full_name || u.email) && (
                    <div className="text-xs text-muted-foreground">
                      {u.full_name}
                      {u.full_name && u.email ? " · " : ""}
                      {u.email}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                    {u.role === "admin" ? (
                      <ShieldCheck className="mr-1 h-3 w-3" />
                    ) : (
                      <UserIcon className="mr-1 h-3 w-3" />
                    )}
                    {u.role}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {u.auth_provider === "oidc" ? "SSO" : "Local"}
                </TableCell>
                <TableCell>
                  {u.is_active ? (
                    <span className="text-sm text-status-healthy">Active</span>
                  ) : (
                    <span className="text-sm text-muted-foreground">Disabled</span>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {u.last_login_at
                    ? new Date(u.last_login_at).toLocaleString()
                    : "Never"}
                </TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" onClick={() => openEdit(u)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={currentUser?.id === u.id}
                    onClick={() => setDeleteUser(u)}
                  >
                    <Trash2 className="h-4 w-4 text-status-down" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add User</DialogTitle>
            <DialogDescription>
              Create a local account with a username and password.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="c-username">Username</Label>
              <Input id="c-username" value={cUsername} onChange={(e) => setCUsername(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-password">Password</Label>
              <Input id="c-password" type="password" value={cPassword} onChange={(e) => setCPassword(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-fullname">Full name (optional)</Label>
              <Input id="c-fullname" value={cFullName} onChange={(e) => setCFullName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-email">Email (optional)</Label>
              <Input id="c-email" type="email" value={cEmail} onChange={(e) => setCEmail(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={cRole} onValueChange={setCRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="operator">Operator — view &amp; control devices</SelectItem>
                  <SelectItem value="admin">Admin — full access</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!cUsername || !cPassword || createUser.isPending}
              onClick={() =>
                createUser.mutate({
                  data: {
                    username: cUsername,
                    password: cPassword,
                    full_name: cFullName || null,
                    email: cEmail || null,
                    role: cRole,
                  },
                })
              }
            >
              {createUser.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editUser} onOpenChange={(o) => !o && setEditUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {editUser?.username}</DialogTitle>
            <DialogDescription>Update role, status, or reset the password.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="e-fullname">Full name</Label>
              <Input id="e-fullname" value={eFullName} onChange={(e) => setEFullName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="e-email">Email</Label>
              <Input id="e-email" type="email" value={eEmail} onChange={(e) => setEEmail(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={eRole} onValueChange={setERole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="operator">Operator</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="e-active">Account active</Label>
              <Switch id="e-active" checked={eActive} onCheckedChange={setEActive} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="e-password">Reset password (optional)</Label>
              <Input
                id="e-password"
                type="password"
                placeholder="Leave blank to keep current"
                value={ePassword}
                onChange={(e) => setEPassword(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)}>
              Cancel
            </Button>
            <Button
              disabled={updateUser.isPending}
              onClick={() =>
                editUser &&
                updateUser.mutate({
                  id: editUser.id,
                  data: {
                    full_name: eFullName || null,
                    email: eEmail || null,
                    role: eRole,
                    is_active: eActive,
                    password: ePassword || null,
                  },
                })
              }
            >
              {updateUser.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteUser} onOpenChange={(o) => !o && setDeleteUser(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleteUser?.username}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the account. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-status-down hover:bg-status-down/90"
              onClick={(e) => {
                e.preventDefault();
                if (deleteUser) deleteUserMut.mutate({ id: deleteUser.id });
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
