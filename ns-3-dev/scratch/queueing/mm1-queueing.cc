#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/traffic-control-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/netanim-module.h"
#include "ns3/mobility-module.h"
#include <sys/stat.h>    // mkdir
#include <sys/types.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("QueueingProject");

// ================= TRACE CALLBACK =================
static void
QueueTrace(Ptr<OutputStreamWrapper> stream,
           uint32_t oldVal,
           uint32_t newVal)
{
    *stream->GetStream()
        << Simulator::Now().GetSeconds()
        << " " << newVal << std::endl;
}

// ================= HELPER: make directory if absent =================
static void
EnsureDir(const std::string &path)
{
    mkdir(path.c_str(), 0755);   // no-op if already exists
}

int main(int argc, char *argv[])
{
    // ================= CONFIGURABLE PARAMETERS =================
    double      simTime    = 15.0;
    std::string rate       = "500Kbps";
    std::string bottleneck = "1Mbps";
    std::string accessRate = "100Mbps";
    std::string accessDelay= "2ms";
    std::string bnDelay    = "10ms";
    std::string qdisc      = "Prio";
    uint32_t    pkt0       = 512;
    uint32_t    pkt1       = 1024;
    uint32_t    pkt2       = 2048;
    // Tag lets you name a run anything you like, e.g. --tag=highLoad
    // If left empty the simulation auto-generates a tag from the parameters.
    std::string tag        = "";

    CommandLine cmd;
    cmd.AddValue("simTime",    "Simulation duration in seconds",                simTime);
    cmd.AddValue("rate",       "Client OnOff data rate (e.g. 500Kbps, 2Mbps)", rate);
    cmd.AddValue("bottleneck", "Bottleneck link capacity (e.g. 1Mbps)",         bottleneck);
    cmd.AddValue("accessRate", "Access link capacity (e.g. 100Mbps)",           accessRate);
    cmd.AddValue("accessDelay","Access link delay (e.g. 2ms)",                  accessDelay);
    cmd.AddValue("bnDelay",    "Bottleneck link delay (e.g. 10ms)",             bnDelay);
    cmd.AddValue("qdisc",      "Queue discipline: Prio | FqCodel | TBF | Fifo", qdisc);
    cmd.AddValue("pkt0",       "Packet size for client 0 in bytes",             pkt0);
    cmd.AddValue("pkt1",       "Packet size for client 1 in bytes",             pkt1);
    cmd.AddValue("pkt2",       "Packet size for client 2 in bytes",             pkt2);
    cmd.AddValue("tag",        "Optional name for this experiment run",         tag);
    cmd.Parse(argc, argv);

    // ── Build an auto-tag from parameters if none was supplied ──
    if (tag.empty())
    {
        // e.g.  "rate2Mbps_bn1Mbps_Prio"
        // Strip non-alphanumeric characters so the folder name is safe
        auto clean = [](std::string s) {
            std::string out;
            for (char c : s)
                if (std::isalnum(c) || c == '.') out += c;
            return out;
        };
        tag = "rate"  + clean(rate)
            + "_bn"   + clean(bottleneck)
            + "_"     + qdisc;
    }

    // ── Output directory for this specific experiment ──
    // All results go into:  results/<tag>/
    std::string outDir = "results/" + tag + "/";
    EnsureDir("results");
    EnsureDir(outDir);

    std::cout << "\n========================================" << std::endl;
    std::cout << "  NS3 Queueing Simulation" << std::endl;
    std::cout << "  Experiment tag : " << tag    << std::endl;
    std::cout << "  Output dir     : " << outDir << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "  simTime    = " << simTime    << " s"   << std::endl;
    std::cout << "  rate       = " << rate                 << std::endl;
    std::cout << "  bottleneck = " << bottleneck           << std::endl;
    std::cout << "  accessRate = " << accessRate           << std::endl;
    std::cout << "  accessDelay= " << accessDelay          << std::endl;
    std::cout << "  bnDelay    = " << bnDelay              << std::endl;
    std::cout << "  qdisc      = " << qdisc                << std::endl;
    std::cout << "  pkt sizes  = " << pkt0 << " / " << pkt1
              << " / " << pkt2 << " bytes"                 << std::endl;
    std::cout << "========================================\n" << std::endl;

    // ================= NODES =================
    NodeContainer clients;  clients.Create(3);
    NodeContainer router;   router.Create(1);
    NodeContainer server;   server.Create(1);

    InternetStackHelper stack;
    stack.InstallAll();

    // ================= LINKS =================
    PointToPointHelper access;
    access.SetDeviceAttribute("DataRate", StringValue(accessRate));
    access.SetChannelAttribute("Delay",   StringValue(accessDelay));

    PointToPointHelper bottleneckLink;
    bottleneckLink.SetDeviceAttribute("DataRate", StringValue(bottleneck));
    bottleneckLink.SetChannelAttribute("Delay",   StringValue(bnDelay));

    // ================= CLIENT LINKS =================
    std::vector<Ipv4InterfaceContainer> clientIf;

    for (uint32_t i = 0; i < clients.GetN(); i++)
    {
        NodeContainer pair(clients.Get(i), router.Get(0));
        NetDeviceContainer dev = access.Install(pair);

        Ipv4AddressHelper addr;
        std::ostringstream subnet;
        subnet << "10.1." << i << ".0";
        addr.SetBase(subnet.str().c_str(), "255.255.255.0");
        clientIf.push_back(addr.Assign(dev));
    }

    // ================= BOTTLENECK LINK =================
    NodeContainer routerServer(router.Get(0), server.Get(0));
    NetDeviceContainer bottleneckDev = bottleneckLink.Install(routerServer);

    Ipv4AddressHelper addr;
    addr.SetBase("10.2.0.0", "255.255.255.0");
    Ipv4InterfaceContainer serverIf = addr.Assign(bottleneckDev);

    // ================= QUEUE DISC =================
    TrafficControlHelper tchDefault;
    tchDefault.Uninstall(bottleneckDev);

    TrafficControlHelper tch;
    if (qdisc == "FqCodel")
        tch.SetRootQueueDisc("ns3::FqCoDelQueueDisc");
    else if (qdisc == "TBF")
        tch.SetRootQueueDisc("ns3::TbfQueueDisc",
                             "Rate",  StringValue(bottleneck),
                             "Burst", UintegerValue(10000),
                             "Mtu",   UintegerValue(0));
    else if (qdisc == "Fifo")
        tch.SetRootQueueDisc("ns3::FifoQueueDisc");
    else
        tch.SetRootQueueDisc("ns3::PrioQueueDisc");

    QueueDiscContainer qdiscs = tch.Install(bottleneckDev);
    Ptr<QueueDisc> queue = qdiscs.Get(0);

    // ================= TRACE =================
    AsciiTraceHelper ascii;
    Ptr<OutputStreamWrapper> stream =
        ascii.CreateFileStream(outDir + "queue-size.tr");

    queue->TraceConnectWithoutContext(
        "PacketsInQueue",
        MakeBoundCallback(&QueueTrace, stream));

    // ================= ROUTING =================
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // ================= SERVER =================
    uint16_t port = 8080;
    PacketSinkHelper sink("ns3::UdpSocketFactory",
        InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApp = sink.Install(server.Get(0));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(simTime));

    // ================= TRAFFIC =================
    uint32_t pktSizes[3] = {pkt0, pkt1, pkt2};

    for (uint32_t i = 0; i < clients.GetN(); i++)
    {
        OnOffHelper app("ns3::UdpSocketFactory",
            InetSocketAddress(serverIf.GetAddress(1), port));
        app.SetAttribute("DataRate",   StringValue(rate));
        app.SetAttribute("PacketSize", UintegerValue(pktSizes[i]));

        ApplicationContainer apps = app.Install(clients.Get(i));
        apps.Start(Seconds(1.0 + i));
        apps.Stop(Seconds(simTime));
    }

    // ================= FLOW MONITOR =================
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    // ================= NODE POSITIONS =================
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.InstallAll();

    clients.Get(0)->GetObject<ConstantPositionMobilityModel>()->SetPosition(Vector(0,   0, 0));
    clients.Get(1)->GetObject<ConstantPositionMobilityModel>()->SetPosition(Vector(0,  20, 0));
    clients.Get(2)->GetObject<ConstantPositionMobilityModel>()->SetPosition(Vector(0,  40, 0));
    router.Get(0) ->GetObject<ConstantPositionMobilityModel>()->SetPosition(Vector(50, 20, 0));
    server.Get(0) ->GetObject<ConstantPositionMobilityModel>()->SetPosition(Vector(100,20, 0));

    // ================= ANIMATION =================
    AnimationInterface anim(outDir + "queueing.xml");

    anim.UpdateNodeDescription(clients.Get(0), "Client 0 (" + std::to_string(pkt0) + "B)");
    anim.UpdateNodeDescription(clients.Get(1), "Client 1 (" + std::to_string(pkt1) + "B)");
    anim.UpdateNodeDescription(clients.Get(2), "Client 2 (" + std::to_string(pkt2) + "B)");
    anim.UpdateNodeDescription(router.Get(0),  "Router [" + qdisc + "]");
    anim.UpdateNodeDescription(server.Get(0),  "Server");

    anim.UpdateNodeColor(clients.Get(0), 0,   128, 255);
    anim.UpdateNodeColor(clients.Get(1), 0,   200, 128);
    anim.UpdateNodeColor(clients.Get(2), 255, 165,   0);
    anim.UpdateNodeColor(router.Get(0),  180,   0, 180);
    anim.UpdateNodeColor(server.Get(0),  220,  50,  50);

    // ================= RUN =================
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    monitor->SerializeToXmlFile(outDir + "flowmon.xml", true, true);

    std::cout << "\n[DONE] Results saved to: " << outDir << std::endl;

    Simulator::Destroy();
    return 0;
}
