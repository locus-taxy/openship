"use client"

import {
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { Button } from "./ui/button"
import { Collapsible } from "./ui/collapsible"
import { Dialog, DialogOverlay, DialogTrigger } from "./ui/dialog"
import { DialogDemo } from "../app/credentialsManager"
import useStore from "../store"
import { LogInIcon, LogOutIcon } from "lucide-react"
import { toast } from "../hooks/use-toast"
import { getRequest } from "../services"

export function NavUser() {
    const { isCredentialsDialog, setIsCredentialsDialog, credentialsNotPresent, setCredentialsNotPresent } = useStore((state: any) => state);

    const setOpen = () => {
        if (credentialsNotPresent) {
            setIsCredentialsDialog(true);
        } else {
            setIsCredentialsDialog(!isCredentialsDialog);
        }
    }

    function clearAllCookies() {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookieName = cookies[i].split('=')[0].trim();
            // Set cookie expiration date to a past date
            document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
    }

    const logoutHandler = async () => {
        await getRequest("/auth/logout");
        clearAllCookies();

        toast({
            title: "Logged out successfully",
            description: "You have been logged out successfully",
        })

        setCredentialsNotPresent(true);
    }

  return (
    <Collapsible
        key="credentials"
        asChild
        defaultOpen={true}
        className="group/collapsible"
    >

        <SidebarMenu className="flex flex-row items-center justify-center">
        <SidebarMenuItem className="w-full">
            <hr />
            <Dialog open={isCredentialsDialog} onOpenChange={setOpen}>
                <DialogOverlay className="fixed inset-0 z-50 backdrop-blur-sm bg-black/30" />
                <DialogTrigger className="mt-2 w-full" asChild>
                    {
                        credentialsNotPresent ? (
                            <Button variant="outline" onClick={setOpen}>
                                <LogInIcon className="w-4 h-4 mr-2" />
                                Login
                            </Button>
                        ) : (
                            <Button variant="outline" onClick={logoutHandler}>
                                <LogOutIcon className="w-4 h-4 mr-2" />
                                Logout
                            </Button>
                        )
                    }
                </DialogTrigger>
                <DialogDemo />
            </Dialog>
            {/* <Button className="mt-2 w-full">Set Credentials</Button> */}
        </SidebarMenuItem>
        </SidebarMenu>
    </Collapsible>
  )
}
