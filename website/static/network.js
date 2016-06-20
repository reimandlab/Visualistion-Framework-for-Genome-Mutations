var Network = (function ()
{
    var width = 600
    var height = 400

    function fitTextIntoCircle(d, context)
    {
        var radius = d.r
        return Math.min(2 * radius, (2 * radius - 8) / context.getComputedTextLength() * 24) + 'px';
    }

    function calculateRadius(mutations_count, is_group)
    {
        is_group = is_group ? 1 : 0

        r = config.minimalRadius
        // the groups are show as two times bigger
        r *= (is_group + 1)
        // more mutations = bigger circle
        r += 6 * Math.log10(mutations_count + 1)

        return r
    }

    var config = {
        minimalRadius: 6,
        ratio: 1
    }

    function configure(new_config)
    {
        for(var key in new_config)
        {
            if(new_config.hasOwnProperty(key))
            {
                config[key] = new_config[key]
            }
        }
    }

    var publicSpace = {
        init: function(user_config)
        {
            configure(user_config)

            height = width * config.ratio

            var force = d3.layout.force()
                .gravity(0.05)
                .distance(100)
                .charge(-100)
                .size([width, height])


            var vis = d3.select(config.element).append('svg')
                .attr('preserveAspectRatio', 'xMinYMin meet')
                .attr('viewBox', '0 0 ' + width + ' ' + height)
                .classed('svg-content-responsive', true)

            var data = config.data

            var links = []

            for(var i = 0; i < data.kinases.length; i++)
            {
                var kinase = data.kinases[i]
                kinase.x = Math.random() * width
                kinase.y = Math.random() * height
                kinase.r = calculateRadius(
                    kinase.protein ? kinase.protein.mutations_count : 0,
                    kinase.is_group
                )
                links.push(
                    {
                        source: i,
                        target: data.kinases.length,
                        weight: 1
                    }
                )
            }

            var nodes_data = data.kinases
            var protein = data.protein
            var protein_node = {
                name: protein.name,
                r: calculateRadius(protein.mutations_count),
                x: (width - r) / 2,
                y: (height - r) / 2,
                color: 'blue'
            }
            nodes_data.push(protein_node)

            force
                .nodes(nodes_data)
                .links(links)
                .start()

            var link = vis.selectAll(".link")
                .data(links)
                .enter().append("line")
                .attr("class", "link")
                .style("stroke-width", function(d) { return Math.sqrt(d.weight); });

            var nodes = vis.selectAll('.node')
                .data(nodes_data)
                .enter().append('g')
                .attr('transform', function(d){return 'translate(' + [d.x, d.y] + ')'})
                .attr('class', 'node')
                .call(force.drag)

            nodes.append('circle')
                .attr('class', 'nodes')
                .attr('r', function(node){ return node.r })
                .attr('stroke', function(node) {
                    var default_color = (node.is_group ? 'red' : '#905590')
                    return node.color || default_color
                }) 

            nodes.append('text')
                .text(function(d){return d.name})
                .style('font-size', function(d) { return fitTextIntoCircle(d, this) })
                .attr('dy', '.35em')
                
            force.on('tick', function() {
                    link.attr("x1", function(d) { return d.source.x })
                        .attr("y1", function(d) { return d.source.y })
                        .attr("x2", function(d) { return d.target.x })
                        .attr("y2", function(d) { return d.target.y })
                    nodes.attr('transform', function(d){return 'translate(' + [d.x, d.y] + ')'})
                    }
                )

        }
    }

    return publicSpace
})()
