import { useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import useStore from "@/store"

export default function SampleApp() {
    const { setPluginName, setPluginInfo } = useStore((state: any) => state);

    useEffect(() => {
        setPluginName("Sample")
        setPluginInfo("This is a sample page.")
    }, [setPluginName, setPluginInfo]);

    return (
        <div className="container mx-auto p-4">
            <Card className="max-w-2xl mx-auto">
                <CardHeader>
                    <CardTitle>Sample</CardTitle>
                </CardHeader>
                <CardContent>
                    <p>This is a sample page.</p>
                </CardContent>
            </Card>
        </div>
    )
}
