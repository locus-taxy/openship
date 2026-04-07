import { useState } from "react";
import { Button } from "@/components/ui/button"
import {
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { EyeIcon, EyeOffIcon, Loader2 } from "lucide-react"
// import { getRequest } from "../../services";
import { useToast } from "@/hooks/use-toast";
import useStore from "../../store";

export function DialogDemo() {
    // @ts-ignore
    const [username, setUsername] = useState("");
    // @ts-ignore
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    const { toast } = useToast();
    const { setIsCredentialsDialog, setCredentialsNotPresent } = useStore((state: any) => state);

    const clearAllCookies = () => {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookieName = cookies[i].split('=')[0].trim();
            document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
    }

    const handleSubmit = async (e: any) => {
        e.preventDefault()
        setIsProcessing(true)

        /** Call Auth API endpoint if you have one

        const url = "/auth/set-credentials";
        const response = await getRequest(url, { username, password });

        if (!response.success) {
            setIsProcessing(false);
            toast({
                variant: "destructive",
                title: "Error",
                description: `Error setting credentials! Either username or password is incorrect. ${response.error.message}`,
            });
            return false;
        }

        const token =  response.data?.token;
        */

        toast({
            variant: "default",
            className: "bg-green-500 text-white",
            title: "Success",
            description: "Credentials have been set successfully",
        });

        clearAllCookies();



        const token = "sampleToken";

        document.cookie = `token=${encodeURIComponent(token)}; from_view=true`
        setIsCredentialsDialog(false);
        setCredentialsNotPresent(false);
        setIsProcessing(false);

    }


    return (
        <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
                <a href="#" className="flex items-center gap-2 self-center font-medium">
                    {/* <img src={} alt="" className="h-8 w-auto" /> */}
                    <span className="font-bold" style={{ fontSize: "22px" }}>AUTH</span>
                </a>
                <DialogTitle></DialogTitle>
            </DialogHeader>
            <form>
                <div className="grid gap-6">
                    <div className="grid gap-6">
                        <div className="grid gap-2">
                            <Label htmlFor="email">Username</Label>
                            <Input
                                id="email"
                                type="email"
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="username"
                                required
                            />
                        </div>
                        <div className="grid gap-2">
                            <div className="flex items-center">
                                <Label htmlFor="password">Password</Label>
                            </div>
                            <div className="relative">
                                <Input
                                    id="password"
                                    onChange={(e) => setPassword(e.target.value)}
                                    type={showPassword ? "text" : "password"}
                                    required
                                />
                                <button
                                    type="button"
                                    className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent" // Button styling
                                    onClick={() => setShowPassword(prev => !prev)} // Toggle showPassword state
                                >
                                    {showPassword ? (
                                        <EyeOffIcon className="h-4 w-4" aria-hidden="true" /> // Icon when password is visible
                                    ) : (
                                        <EyeIcon className="h-4 w-4" aria-hidden="true" /> // Icon when password is hidden
                                    )}
                                    <span className="sr-only">{showPassword ? 'Hide password' : 'Show password'}</span>
                                </button>
                            </div>
                        </div>
                        <Button type="submit" disabled={isProcessing} className="w-full" onClick={handleSubmit}>
                            {isProcessing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {isProcessing ? "Logging in..." : "Login"}
                        </Button>
                    </div>
                </div>
            </form>
        </DialogContent>
    )
}
